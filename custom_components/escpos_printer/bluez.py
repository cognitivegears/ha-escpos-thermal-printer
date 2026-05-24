"""bluez (org.bluez) D-Bus helpers used by the config flow and sensor platform.

These helpers are the integration's only direct dependency on ``dbus-fast``.
They gracefully degrade when ``dbus-fast`` isn't importable (non-Linux,
missing optional dep) or the system bus isn't reachable (rootless Docker,
no ``/run/dbus`` mount in HA Container) — every public function returns a
sensible "unknown" sentinel rather than raising.

Functions:

* :func:`list_paired_bluetooth_devices` — enumerate already-paired BT
  devices including their Class-of-Device (used by the config flow's
  picker; imaging-class filtering happens at the helper level).
* :func:`query_bt_battery_percentage` — read
  ``org.bluez.Battery1.Percentage`` for a given MAC; used by the battery
  sensor entity. Returns ``None`` when the device doesn't expose
  ``Battery1`` (most cheap thermal printers don't).
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from .security import validate_bluetooth_mac

_LOGGER = logging.getLogger(__name__)


# Class-of-Device — Major Device Class field (bits 8-12).
# Major class 0x06 = "Imaging" — covers thermal printers, label printers,
# and most ESC/POS receipt printers.
_BT_MAJOR_CLASS_IMAGING = 0x06


def is_imaging_device(class_value: int | None) -> bool:
    """Return True if the bluez Class-of-Device value is the Imaging major class."""
    if class_value is None:
        return False
    return ((class_value >> 8) & 0x1F) == _BT_MAJOR_CLASS_IMAGING


def _normalize_mac(mac: Any) -> str | None:
    """Validate-and-normalize a MAC; ``None`` on bad input. Discovery-loop friendly."""
    if not isinstance(mac, str):
        return None
    try:
        from homeassistant.exceptions import HomeAssistantError  # noqa: PLC0415

        return validate_bluetooth_mac(mac)
    except HomeAssistantError:
        return None
    except Exception:
        return None


async def _connect_system_bus() -> Any | None:
    """Open the system D-Bus or return ``None`` (logged at INFO).

    Centralizes the dbus-fast import + connect + graceful-degrade pattern
    used by every public helper here.
    """
    try:
        from dbus_fast import BusType  # noqa: PLC0415
        from dbus_fast.aio import MessageBus  # noqa: PLC0415
    except ImportError:
        _LOGGER.info("dbus-fast not available; skipping bluez query")
        return None

    try:
        return await MessageBus(bus_type=BusType.SYSTEM).connect()
    except Exception as exc:
        _LOGGER.info("System D-Bus not reachable (%s); skipping bluez query", exc)
        return None


async def _get_managed_objects(bus: Any) -> dict[str, Any] | None:
    """Call ``ObjectManager.GetManagedObjects`` on ``org.bluez/`` or return ``None``."""
    try:
        introspection = await bus.introspect("org.bluez", "/")
        proxy = bus.get_proxy_object("org.bluez", "/", introspection)
        obj_manager = proxy.get_interface("org.freedesktop.DBus.ObjectManager")
        return await obj_manager.call_get_managed_objects()  # type: ignore[no-any-return]
    except Exception as exc:
        _LOGGER.info("Failed to query bluez managed objects: %s", exc)
        return None


async def list_paired_bluetooth_devices() -> list[dict[str, Any]]:
    """Enumerate Bluetooth devices paired on the host.

    Returns a list of ``{mac, name, alias, label, class, is_imaging,
    _choice_key}`` dicts. Returns an empty list when bluez isn't reachable
    so callers can degrade to manual MAC entry.
    """
    bus = await _connect_system_bus()
    if bus is None:
        return []
    try:
        managed = await _get_managed_objects(bus)
    finally:
        with contextlib.suppress(Exception):
            bus.disconnect()
    if managed is None:
        return []

    devices: list[dict[str, Any]] = []
    for ifaces in managed.values():
        device_props = ifaces.get("org.bluez.Device1")
        if not device_props:
            continue
        paired_var = device_props.get("Paired")
        if paired_var is None or not bool(getattr(paired_var, "value", False)):
            continue
        mac_var = device_props.get("Address")
        if mac_var is None:
            continue
        mac = _normalize_mac(getattr(mac_var, "value", ""))
        if mac is None:
            continue
        alias_var = device_props.get("Alias") or device_props.get("Name")
        alias = getattr(alias_var, "value", "") if alias_var is not None else ""
        label = f"{alias} ({mac})" if alias else mac
        class_var = device_props.get("Class")
        class_value: int | None = (
            int(getattr(class_var, "value", 0)) if class_var is not None else None
        )
        devices.append(
            {
                "mac": mac,
                "name": alias or mac,
                "alias": alias,
                "label": label,
                "class": class_value,
                "is_imaging": is_imaging_device(class_value),
                "_choice_key": mac,
            }
        )
    return devices


async def query_bt_battery_percentage(mac: str) -> int | None:  # noqa: PLR0911
    """Read ``org.bluez.Battery1.Percentage`` for ``mac``, or return ``None``.

    Returns ``None`` when bluez isn't reachable, the device isn't tracked,
    or the device doesn't expose ``Battery1`` (most cheap thermal printers
    don't). Callers should mark the corresponding entity as unavailable.
    """
    target_mac = (mac or "").upper()
    if not target_mac:
        return None

    bus = await _connect_system_bus()
    if bus is None:
        return None
    try:
        managed = await _get_managed_objects(bus)
    finally:
        with contextlib.suppress(Exception):
            bus.disconnect()
    if managed is None:
        return None

    for ifaces in managed.values():
        device_props = ifaces.get("org.bluez.Device1")
        if not device_props:
            continue
        mac_var = device_props.get("Address")
        if mac_var is None:
            continue
        if str(getattr(mac_var, "value", "")).upper() != target_mac:
            continue
        battery_props = ifaces.get("org.bluez.Battery1")
        if battery_props is None:
            return None
        pct_var = battery_props.get("Percentage")
        if pct_var is None:
            return None
        try:
            value = int(getattr(pct_var, "value", -1))
        except (ValueError, TypeError):
            return None
        return value if 0 <= value <= 100 else None
    return None
