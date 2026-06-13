"""Configuration dataclasses for printer adapters.

B-L6: these dataclasses are intentionally NOT ``frozen=True``. The
single mutation in ``base_adapter.__init__`` rewrites ``timeout`` after
running it through ``validate_timeout``; making the classes frozen
would force constructing a replacement instance there, adding a tiny
allocation per adapter setup for no real safety win (the integration
never shares config instances across adapters). They use plain
``@dataclass`` to keep that in-place rewrite legal; ``slots=True``
would also be fine but isn't applied uniformly because the few config
types that *don't* get the timeout rewrite already inherit slots
behaviour from ``BasePrinterConfig`` if we add it there. Status
flagged here so the next contributor understands the asymmetry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..const import (
    DEFAULT_BAUDRATE,
    DEFAULT_IN_EP,
    DEFAULT_OUT_EP,
    DEFAULT_RFCOMM_CHANNEL,
    DEFAULT_SERIAL_WRITE_CHUNK_DELAY_MS,
    DEFAULT_SERIAL_WRITE_CHUNK_SIZE,
)


@dataclass
class BasePrinterConfig:
    """Base printer configuration shared by all connection types.

    Not frozen — ``base_adapter.__init__`` rewrites ``timeout`` once
    after validation. See module docstring for the rationale.
    """

    codepage: str | None = None
    profile: str | None = None
    line_width: int = 48
    timeout: float = 4.0
    # Opt-in: permit image URLs that resolve to private/LAN/loopback
    # addresses. Off by default; the always-unsafe ranges (link-local
    # metadata, multicast, reserved) stay blocked regardless.
    allow_local_image_urls: bool = False


@dataclass
class NetworkPrinterConfig(BasePrinterConfig):
    """Configuration for network (TCP/IP) printers."""

    connection_type: Literal["network"] = field(default="network", repr=False)
    host: str = ""
    port: int = 9100


@dataclass
class UsbPrinterConfig(BasePrinterConfig):
    """Configuration for USB printers."""

    connection_type: Literal["usb"] = field(default="usb", repr=False)
    vendor_id: int = 0
    product_id: int = 0
    in_ep: int = DEFAULT_IN_EP
    out_ep: int = DEFAULT_OUT_EP


@dataclass
class BluetoothPrinterConfig(BasePrinterConfig):
    """Configuration for Bluetooth Classic / RFCOMM printers."""

    connection_type: Literal["bluetooth"] = field(default="bluetooth", repr=False)
    mac: str = ""
    rfcomm_channel: int = DEFAULT_RFCOMM_CHANNEL


@dataclass
class SerialPrinterConfig(BasePrinterConfig):
    """Configuration for serial (UART/RS-232) printers.

    ``serial_port`` accepts a filesystem path (``/dev/ttyUSB0``, ``COM3``)
    *or* a serialx URL (``esphome://host:port``, ``rfc2217://host:port``,
    ``socket://host:port``). The baudrate field is passed through for all
    connection types.
    """

    connection_type: Literal["serial"] = field(default="serial", repr=False)
    serial_port: str = ""
    baudrate: int = DEFAULT_BAUDRATE
    write_chunk_size: int = DEFAULT_SERIAL_WRITE_CHUNK_SIZE
    write_chunk_delay_ms: int = DEFAULT_SERIAL_WRITE_CHUNK_DELAY_MS


# Type alias for config union (use for type hints)
PrinterConfigTypes = NetworkPrinterConfig | UsbPrinterConfig | BluetoothPrinterConfig | SerialPrinterConfig

# Backward-compatible alias: PrinterConfig(...) still works and creates NetworkPrinterConfig
# This maintains API compatibility for existing code that instantiates PrinterConfig directly
PrinterConfig = NetworkPrinterConfig
