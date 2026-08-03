"""Shared DeviceInfo construction for all ESC/POS entity platforms.

Single home for the identifiers/name/manufacturer/model DeviceInfo that
binary_sensor.py, sensor.py, and notify.py each used to build independently
(and could silently drift out of sync when a new connection type landed).
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
    DOMAIN,
)

_MODEL_BY_CONNECTION_TYPE = {
    CONNECTION_TYPE_USB: "USB Printer",
    CONNECTION_TYPE_BLUETOOTH: "Bluetooth Printer",
    CONNECTION_TYPE_SERIAL: "Serial Printer",
}


def _usb_serial_number(entry: ConfigEntry) -> str | None:
    """Best-effort USB serial number: entry.data first, else unique_id.

    Config flow captures the serial during USB discovery (see
    _config_flow/usb_helpers.py:158-175) but folds it straight into the
    entry's unique_id (``usb:VID:PID[:serial]``) rather than persisting it
    as its own entry.data key. Check entry.data anyway in case a future
    flow starts storing it directly.

    Note: the ``len(parts) == 4`` split below drops the serial number if
    it itself contains a ``:`` (the id would then have more than 4
    colon-separated parts). This is a deliberate trade-off, not an
    oversight -- it keeps the endpoint-suffixed manual-entry id
    (``usb:vid:pid:in_ep:out_ep``, 5 parts) from being misparsed as a
    serial number.
    """
    serial = entry.data.get("serial_number")
    if serial:
        return str(serial)
    unique_id = getattr(entry, "unique_id", None)
    if not unique_id:
        return None
    parts = unique_id.split(":")
    if len(parts) == 4 and parts[0] == "usb":
        return parts[3] or None
    return None


def build_device_info(entry: ConfigEntry) -> DeviceInfo:
    """Build the DeviceInfo shared by every entity on a config entry."""
    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
    model = _MODEL_BY_CONNECTION_TYPE.get(connection_type, "Network Printer")

    info = DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"ESC/POS Printer {entry.title}",
        manufacturer="ESC/POS",
        model=model,
    )
    if connection_type == CONNECTION_TYPE_USB:
        serial = _usb_serial_number(entry)
        if serial:
            info["serial_number"] = serial
    return info
