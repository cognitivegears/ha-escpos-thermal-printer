"""Scan for and pair Bluetooth Classic printers through bluez (D-Bus).

Home Assistant's Bluetooth integration never pairs Classic devices, so
this module lets the config flow do what ``bluetoothctl scan on`` /
``pair`` / ``trust`` would do by hand:

* :func:`discover_bluetooth_devices` runs a short BR/EDR inquiry and returns
  every device bluez knows afterwards, paired or not.
* :func:`pair_bluetooth_device` pairs one device with a throw-away bluez
  agent that answers PIN, passkey and confirmation requests, then marks it
  trusted so bluez reconnects it after reboots.

Like :mod:`bluez`, every function degrades to a "nothing happened" result
when ``dbus-fast`` or the system bus is unavailable instead of raising.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import logging
from typing import Any

from ._bluez_agent import build_pairing_agent_class
from .bluez import (
    _connect_system_bus,
    _get_managed_objects,
    _normalize_mac,
    parse_bluez_devices,
)

_LOGGER = logging.getLogger(__name__)

BLUEZ_SERVICE = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
DEVICE_IFACE = "org.bluez.Device1"
AGENT_MANAGER_IFACE = "org.bluez.AgentManager1"
AGENT_PATH = "/org/escpos_printer/pairing_agent"

# KeyboardDisplay is the capability that lets one agent answer every
# pairing variant (legacy PIN, passkey entry, numeric comparison).
AGENT_CAPABILITY = "KeyboardDisplay"

# Seconds a BR/EDR inquiry needs to see most devices in range.
DEFAULT_SCAN_SECONDS = 12.0
PAIR_TIMEOUT_SECONDS = 30.0

# Legacy PINs that thermal printers ship with, tried in this order before
# the user is asked for one.
DEFAULT_PIN_CANDIDATES: tuple[str, ...] = ("0000", "1234")

# Stable error codes; the config flow maps them to strings.json keys.
PAIR_ERROR_UNAVAILABLE = "unavailable"
PAIR_ERROR_NOT_FOUND = "not_found"
PAIR_ERROR_AUTH_FAILED = "auth_failed"
PAIR_ERROR_AUTH_REJECTED = "auth_rejected"
PAIR_ERROR_TIMEOUT = "timeout"
PAIR_ERROR_UNREACHABLE = "unreachable"
PAIR_ERROR_BUSY = "busy"
PAIR_ERROR_FAILED = "failed"

_BLUEZ_ERROR_TO_CODE: dict[str, str] = {
    "org.bluez.Error.AuthenticationFailed": PAIR_ERROR_AUTH_FAILED,
    "org.bluez.Error.AuthenticationRejected": PAIR_ERROR_AUTH_REJECTED,
    "org.bluez.Error.AuthenticationCanceled": PAIR_ERROR_AUTH_REJECTED,
    "org.bluez.Error.AuthenticationTimeout": PAIR_ERROR_TIMEOUT,
    "org.bluez.Error.ConnectionAttemptFailed": PAIR_ERROR_UNREACHABLE,
    "org.bluez.Error.InProgress": PAIR_ERROR_BUSY,
    "org.bluez.Error.NotReady": PAIR_ERROR_UNAVAILABLE,
    "org.bluez.Error.DoesNotExist": PAIR_ERROR_NOT_FOUND,
}
_ERROR_ALREADY_EXISTS = "org.bluez.Error.AlreadyExists"


@dataclass(frozen=True)
class PairingResult:
    """Outcome of :func:`pair_bluetooth_device`."""

    success: bool
    error: str | None = None


def classify_bluez_error(error_type: str | None) -> str:
    """Map a ``org.bluez.Error.*`` name to a ``PAIR_ERROR_*`` code."""
    return _BLUEZ_ERROR_TO_CODE.get(error_type or "", PAIR_ERROR_FAILED)


def _find_object_path(
    managed: dict[str, Any], interface: str, mac: str | None = None
) -> str | None:
    """Return the first object path exposing ``interface`` (optionally for ``mac``)."""
    for path, ifaces in managed.items():
        props = ifaces.get(interface)
        if props is None:
            continue
        if mac is None:
            return str(path)
        address = props.get("Address")
        if address is not None and str(getattr(address, "value", "")).upper() == mac:
            return str(path)
    return None


def _is_paired(managed: dict[str, Any], path: str) -> bool:
    paired = managed.get(path, {}).get(DEVICE_IFACE, {}).get("Paired")
    return bool(getattr(paired, "value", False))


async def _proxy_interface(bus: Any, path: str, interface: str) -> Any:
    introspection = await bus.introspect(BLUEZ_SERVICE, path)
    return bus.get_proxy_object(BLUEZ_SERVICE, path, introspection).get_interface(interface)


async def discover_bluetooth_devices(
    duration: float = DEFAULT_SCAN_SECONDS,
) -> list[dict[str, Any]]:
    """Run a BR/EDR inquiry for ``duration`` seconds and list every known device.

    Paired devices come first, then the rest by signal strength. Returns an
    empty list when bluez or an adapter isn't reachable.
    """
    bus = await _connect_system_bus()
    if bus is None:
        return []
    try:
        managed = await _get_managed_objects(bus)
        adapter_path = _find_object_path(managed or {}, ADAPTER_IFACE)
        if adapter_path is None:
            _LOGGER.info("No Bluetooth adapter found; skipping discovery scan")
            return []
        await _run_inquiry(bus, adapter_path, duration)
        managed = await _get_managed_objects(bus)
    except Exception as exc:
        _LOGGER.info("Bluetooth discovery scan failed: %s", exc)
        return []
    finally:
        with contextlib.suppress(Exception):
            bus.disconnect()
    if managed is None:
        return []
    devices = parse_bluez_devices(managed, paired_only=False)
    devices.sort(key=lambda d: (not d["paired"], -(d["rssi"] if d["rssi"] is not None else -999)))
    return devices


async def _run_inquiry(bus: Any, adapter_path: str, duration: float) -> None:
    """Start discovery on one adapter, wait, and stop it again."""
    from dbus_fast import Variant  # noqa: PLC0415

    adapter = await _proxy_interface(bus, adapter_path, ADAPTER_IFACE)
    # Classic printers speak RFCOMM, so ignore LE-only advertisers.
    with contextlib.suppress(Exception):
        await adapter.call_set_discovery_filter({"Transport": Variant("s", "bredr")})
    await adapter.call_start_discovery()
    try:
        await asyncio.sleep(duration)
    finally:
        with contextlib.suppress(Exception):
            await adapter.call_stop_discovery()


async def pair_bluetooth_device(
    mac: str,
    *,
    pin: str | None = None,
    timeout: float = PAIR_TIMEOUT_SECONDS,
) -> PairingResult:
    """Pair and trust the device with address ``mac``.

    Without ``pin`` the usual printer defaults (:data:`DEFAULT_PIN_CANDIDATES`)
    are tried in turn; with a ``pin`` only that one is. A ``PAIR_ERROR_AUTH_FAILED``
    result means no PIN worked and the caller should ask the user for one.
    """
    normalized = _normalize_mac(mac)
    if normalized is None:
        return PairingResult(False, PAIR_ERROR_NOT_FOUND)
    bus = await _connect_system_bus()
    if bus is None:
        return PairingResult(False, PAIR_ERROR_UNAVAILABLE)
    try:
        return await _pair_with_agent(
            bus, normalized, (pin,) if pin else DEFAULT_PIN_CANDIDATES, timeout
        )
    except Exception as exc:
        _LOGGER.info("Bluetooth pairing with %s failed unexpectedly: %s", normalized, exc)
        return PairingResult(False, PAIR_ERROR_FAILED)
    finally:
        with contextlib.suppress(Exception):
            bus.disconnect()


async def _pair_with_agent(
    bus: Any, mac: str, pins: tuple[str, ...], timeout: float
) -> PairingResult:
    managed = await _get_managed_objects(bus) or {}
    device_path = _find_object_path(managed, DEVICE_IFACE, mac)
    if device_path is None:
        return PairingResult(False, PAIR_ERROR_NOT_FOUND)

    device = await _proxy_interface(bus, device_path, DEVICE_IFACE)
    if not _is_paired(managed, device_path):
        result = await _pair_with_pins(bus, device, pins, timeout)
        if not result.success:
            return result
    # Trust is what makes bluez reconnect the printer after a reboot.
    await device.set_trusted(True)
    return PairingResult(True)


async def _pair_with_pins(
    bus: Any, device: Any, pins: tuple[str, ...], timeout: float
) -> PairingResult:
    """Register the agent and call ``Device1.Pair`` once per candidate PIN."""
    agent = build_pairing_agent_class()()
    bus.export(AGENT_PATH, agent)
    manager = await _proxy_interface(bus, "/org/bluez", AGENT_MANAGER_IFACE)
    await manager.call_register_agent(AGENT_PATH, AGENT_CAPABILITY)
    try:
        result = PairingResult(False, PAIR_ERROR_FAILED)
        for candidate in pins:
            agent.pin = candidate
            result = await _call_pair(device, timeout)
            if result.success or result.error != PAIR_ERROR_AUTH_FAILED:
                break
        return result
    finally:
        with contextlib.suppress(Exception):
            await manager.call_unregister_agent(AGENT_PATH)
        with contextlib.suppress(Exception):
            bus.unexport(AGENT_PATH)


async def _call_pair(device: Any, timeout: float) -> PairingResult:
    """Call ``Device1.Pair`` once, translating bluez errors to a result."""
    from dbus_fast import DBusError  # noqa: PLC0415

    try:
        async with asyncio.timeout(timeout):
            await device.call_pair()
    except TimeoutError:
        with contextlib.suppress(Exception):
            await device.call_cancel_pairing()
        return PairingResult(False, PAIR_ERROR_TIMEOUT)
    except DBusError as exc:
        if exc.type == _ERROR_ALREADY_EXISTS:
            return PairingResult(True)
        code = classify_bluez_error(exc.type)
        _LOGGER.debug("Pairing attempt rejected by bluez: %s (%s)", exc.type, code)
        return PairingResult(False, code)
    return PairingResult(True)
