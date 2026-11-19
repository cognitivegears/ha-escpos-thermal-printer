"""Async GATT transport for LuckPrinter raster jobs."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager, suppress
import logging
from struct import pack, unpack_from
from types import ModuleType
from typing import TYPE_CHECKING
from zlib import compress

from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError
from bleak.uuids import normalize_uuid_str
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.exceptions import HomeAssistantError

from ..capabilities.ble_profiles import (
    CRAFTSCO_4777_DIALECT,
    craftsco_4777_variant,
    is_craftsco_4777_name,
)
from ..const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..capabilities.ble_profiles import BlePrinterProfile

_LOGGER = logging.getLogger(__name__)

# Characteristic pairs exposed by LuckPrinter firmware. Use the pair on the
# same service so replies arrive on the UART used for writes.
_UARTS = (
    ("ff02", "ff01"),
    ("2af1", "2af0"),
    ("bef8d6c9-9c21-4c9e-b632-bd58c1009f9f", "bef8d6c9-9c21-4c9e-b632-bd58c1009f9f"),
    ("49535343-8841-43f4-a8d4-ecbe34729bb3", "49535343-1e4d-4bd9-ba61-23c647249616"),
)
BLE_PRINTER_SERVICES = frozenset(
    normalize_uuid_str(uuid)
    for uuid in (
        "ff00",
        "18f0",
        "e7810a71-73ae-499d-8c15-faa9aef0c3f2",
        "49535343-fe7d-4ae5-8fa9-9fafd205e455",
    )
)
BLE_ERRORS = (BleakError, OSError, TimeoutError)
_DEFAULT_ATT_PAYLOAD = 20
_MAX_CHUNK = 200
_COMPRESSED_CHUNK = 100
_COMPRESSED_CHUNK_DELAY = 0.04
_REPLY_TIMEOUT = 5
_PRINT_TIMEOUT = 60
_FATAL_STATUS = 0x56  # Cover open, paper out, or printhead overheated.


class BlePrinterMismatchError(Exception):
    """The printer's GATT service or reported model does not match the profile."""


def _uart(
    client: BleakClientWithServiceCache,
) -> tuple[BleakGATTCharacteristic, BleakGATTCharacteristic]:
    for write_uuid, notify_uuid in _UARTS:
        for service in client.services:
            write = service.get_characteristic(normalize_uuid_str(write_uuid))
            notify = service.get_characteristic(normalize_uuid_str(notify_uuid))
            if (
                write is not None
                and notify is not None
                and {"write", "write-without-response"}.intersection(write.properties)
                and {"notify", "indicate"}.intersection(notify.properties)
            ):
                return write, notify
    raise BlePrinterMismatchError


def _match_ack(data: bytes) -> bool:
    if len(data) >= 2 and data[0] == 0xFF:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="ble_printer_error")
    return data.startswith((b"\xaa", b"OK"))


def _compressed_raster(raster: bytes) -> bytes:
    """Convert the rendered GS v 0 bitmap to a LuckPrinter 1F 10 frame."""
    stride, rows = unpack_from("<HH", raster, 4)
    payload = compress(raster[8:], wbits=10)
    return b"\x1f\x10" + pack(">HHI", stride, rows, len(payload)) + payload


class BlePrinterLink:
    """One BLE UART connection with serialized requests and paced GATT writes."""

    def __init__(
        self,
        client: BleakClientWithServiceCache,
        write: BleakGATTCharacteristic,
        advertised_name: str = "",
    ) -> None:
        self.advertised_name = advertised_name
        self._client = client
        self._write = write
        self._with_response = "write-without-response" not in write.properties
        self._notifications: asyncio.Queue[bytes] = asyncio.Queue(maxsize=32)
        self._discarded_raster = False

    def received(self, _characteristic: BleakGATTCharacteristic, data: bytearray) -> None:
        """Queue a notification for the active request."""
        if len(data) == 6 and data.startswith(b"\xff\x10"):
            self._discarded_raster = True
        if not self._notifications.full():
            self._notifications.put_nowait(bytes(data))

    async def write(self, payload: bytes, *, compressed_raster: bool = False) -> None:
        """Write bounded ATT chunks, pacing writes without response."""
        size = _DEFAULT_ATT_PAYLOAD
        if not self._with_response:
            size = max(1, min(_MAX_CHUNK, self._write.max_write_without_response_size))
        if compressed_raster:
            size = min(size, _COMPRESSED_CHUNK)
        for offset in range(0, len(payload), size):
            self._check_raster_buffer()
            async with asyncio.timeout(_REPLY_TIMEOUT):
                await self._client.write_gatt_char(
                    self._write, payload[offset : offset + size], response=self._with_response
                )
            if compressed_raster:
                await asyncio.sleep(_COMPRESSED_CHUNK_DELAY)
            elif not self._with_response:
                await asyncio.sleep(0.02)

    def _check_raster_buffer(self) -> None:
        if self._discarded_raster:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="ble_buffer_overrun"
            )

    async def request(
        self, command: bytes, accepts: Callable[[bytes], bool], timeout: float = _REPLY_TIMEOUT
    ) -> bytes:
        """Send a command and wait for a reply matching it."""
        while not self._notifications.empty():
            self._notifications.get_nowait()
        await self.write(command)
        try:
            async with asyncio.timeout(timeout):
                previous = b""
                while True:
                    response = await self._notifications.get()
                    self._check_raster_buffer()
                    if accepts(response):
                        return response
                    if previous == b"O" and response == b"K" and accepts(b"OK"):
                        return b"OK"
                    previous = response
        except TimeoutError as err:
            raise TimeoutError(f"No reply to BLE command {command.hex(' ')}") from err

    async def read_model(self) -> str:
        """Read the model name without altering printer settings."""

        def is_name(data: bytes) -> bool:
            name = data.strip(b"\x00\r\n ")
            return len(name) > 2 and name.isascii() and name.decode().isprintable()

        response = await self.request(b"\x10\xff\x20\xf0", is_name)
        return response.decode("ascii").strip("\x00\r\n ")

    async def print_job(
        self, profile: BlePrinterProfile, raster: bytes, feed_dots: int, density: int | None
    ) -> None:
        """Send one raster job and wait for the printer to acknowledge completion."""
        is_4777 = profile.dialect == CRAFTSCO_4777_DIALECT
        if raster and is_craftsco_4777_name(self.advertised_name) and not is_4777:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="ble_use_4777_profile"
            )
        (status,) = await self.request(
            b"\x10\xff\x40", lambda data: len(data) == 1 and data[0] < 0x80
        )
        if status & _FATAL_STATUS:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="ble_printer_error")
        variant = None
        if is_4777:
            model = await self.read_model()
            variant = craftsco_4777_variant(self.advertised_name, model)
            if variant is None:
                raise BlePrinterMismatchError("Unrecognized Crafts&Co 4777 firmware")
            _LOGGER.debug("Crafts&Co 4777 raster protocol: %s", variant)
            if variant == "compressed" and raster:
                raster = await asyncio.to_thread(_compressed_raster, raster)

        if density is not None:
            await self.request(b"\x10\xff\x10\x00" + bytes([density]), _match_ack)

        aiyin = profile.dialect == "aiyin" or variant == "aiyin"
        await self._start_job(aiyin=aiyin, continuous=not profile.label_rows)

        if raster:
            if variant == "compressed":
                _LOGGER.debug("Sending %d bytes of compressed BLE raster", len(raster))
                await self.write(raster, compressed_raster=True)
            else:
                await self.write(raster)
            await asyncio.sleep(0.5)
        if profile.label_rows:
            await self.write(b"\x1d\x0c")
            await asyncio.sleep(0.3)
        else:
            await self._feed(feed_dots)
            if variant == "lujiang":
                await self.write(b"\x1b\xbb\xbb")

        stop = b"\x10\xff\xfe\x45" if aiyin else b"\x10\xff\xf1\x45"
        await self.request(stop, _match_ack, _PRINT_TIMEOUT)

    async def _start_job(self, *, aiyin: bool, continuous: bool) -> None:
        if not aiyin:
            await self.write(b"\x10\xff\xf1\x03")
            await self.write(bytes(12))
            return
        if continuous:
            await self.write(b"\x10\xff\x84\x02")
        else:
            await self.request(b"\x10\xff\x84\x00", _match_ack)
        await self.write(bytes(12))
        await self.write(b"\x10\xff\xfe\x01")

    async def _feed(self, dots: int) -> None:
        for offset in range(0, dots, 255):
            await self.write(b"\x1bJ" + bytes([min(255, dots - offset)]))


def bluetooth_api(hass: HomeAssistant) -> ModuleType | None:
    """Access Home Assistant's Bluetooth API only when the integration is loaded."""
    if "bluetooth" not in hass.config.components:
        return None
    from homeassistant.components import bluetooth  # noqa: PLC0415

    return bluetooth


@asynccontextmanager
async def open_ble_printer(
    hass: HomeAssistant, mac: str, timeout: float
) -> AsyncIterator[BlePrinterLink]:
    """Connect through Home Assistant's active adapter or Bluetooth proxy."""
    bluetooth = bluetooth_api(hass)
    device = (
        bluetooth.async_ble_device_from_address(hass, mac, connectable=True) if bluetooth else None
    )
    if device is None:
        raise BleakError("BLE printer is not visible to a connectable scanner")
    info = bluetooth.async_last_service_info(hass, mac, connectable=True) if bluetooth else None
    advertised_name = info.name if info else device.name
    async with asyncio.timeout(timeout):
        client = await establish_connection(
            BleakClientWithServiceCache, device, "BLE printer", max_attempts=2
        )
    try:
        write, notify = _uart(client)
        link = BlePrinterLink(client, write, advertised_name or "")
        async with asyncio.timeout(_REPLY_TIMEOUT):
            await client.start_notify(notify, link.received)
        yield link
    finally:
        with suppress(*BLE_ERRORS):
            async with asyncio.timeout(_REPLY_TIMEOUT):
                await client.disconnect()
