"""Bluetooth Classic / RFCOMM discovery and connectivity helpers for config flow.

Pairing happens outside the integration (host ``bluetoothctl`` or HA OS
Settings → System → Hardware). This module only:

* Lists already-paired devices via ``org.bluez`` over the system D-Bus, when
  reachable. If D-Bus isn't reachable (rootless Docker, missing socket
  mount, non-Linux) we return an empty list and the flow surfaces a manual
  MAC entry path.
* Probes RFCOMM connectivity with a short ``AF_BLUETOOTH`` open via the
  shared transport seam (so tests can swap it for a TCP-loopback variant).
"""

from __future__ import annotations

import contextlib
import errno
import logging
from typing import Any

from homeassistant.exceptions import HomeAssistantError

from ..bluez import is_imaging_device, list_paired_bluetooth_devices
from ..const import BT_MANUAL_ENTRY_KEY, BT_SHOW_ALL_KEY
from ..printer import bluetooth_transport
from ..security import sanitize_log_message, validate_bluetooth_mac

_LOGGER = logging.getLogger(__name__)


# Public re-export so existing imports (`_is_imaging_device`) keep working.
_is_imaging_device = is_imaging_device


# errno -> error_code, evaluated first; substring matching only when errno is None.
_BT_ERRNO_TO_CODE: dict[int, str] = {
    errno.EACCES: "permission_denied",
    errno.EPERM: "permission_denied",
    errno.ETIMEDOUT: "timeout",
    errno.EHOSTUNREACH: "host_down",
    errno.ENETUNREACH: "host_down",
    errno.ECONNREFUSED: "channel_refused",
    errno.ENODEV: "device_not_found",
    errno.EAFNOSUPPORT: "unavailable",
    errno.EPROTONOSUPPORT: "unavailable",
}
# EHOSTDOWN is Linux-only; map it here too when present.
if (_eh := getattr(errno, "EHOSTDOWN", None)) is not None:
    _BT_ERRNO_TO_CODE[_eh] = "host_down"


def _normalize_bt_mac(mac: Any) -> str | None:
    """Return canonical upper-case ``XX:XX:XX:XX:XX:XX`` MAC, or ``None`` if invalid.

    Thin wrapper around :func:`security.validate_bluetooth_mac` that swaps the
    raise-on-invalid contract for a return-None contract — discovery loops
    want to skip invalid entries silently, not raise.
    """
    if not isinstance(mac, str):
        return None
    try:
        return validate_bluetooth_mac(mac)
    except HomeAssistantError:
        return None


def _generate_bt_unique_id(mac: str) -> str:
    """Generate a unique ID for a Bluetooth printer."""
    return f"bt:{mac.lower()}"


_BT_ERROR_KEY_MAP: dict[str, str] = {
    "permission_denied": "bt_permission_denied",
    "device_not_found": "bt_device_not_found",
    "host_down": "bt_host_down",
    "timeout": "bt_timeout",
    "unavailable": "bt_unavailable",
    "channel_refused": "bt_channel_refused",
}


def _bt_error_to_key(error_code: str | None) -> str:
    """Convert a Bluetooth error code to a strings.json error key."""
    return _BT_ERROR_KEY_MAP.get(error_code or "", "cannot_connect_bt")


def _classify_bt_error(exc: OSError) -> str | None:  # noqa: PLR0911
    """Map an OSError from RFCOMM open to a stable error code.

    Returns ``None`` if the error doesn't match any recognized pattern; the
    caller surfaces that as the generic ``cannot_connect_bt`` key.
    """
    err_no = getattr(exc, "errno", None)
    if err_no in _BT_ERRNO_TO_CODE:
        return _BT_ERRNO_TO_CODE[err_no]
    # Substring fallback only when errno is missing (some kernel/libc paths
    # raise OSError with no errno populated).
    text = str(exc).lower()
    if "permission" in text or "access denied" in text:
        return "permission_denied"
    if "timed out" in text:
        return "timeout"
    if "host is down" in text or "unreachable" in text or "no route" in text:
        return "host_down"
    if "connection refused" in text:
        return "channel_refused"
    if "address family not supported" in text or "not available on this platform" in text:
        return "unavailable"
    if "no such device" in text or "not found" in text:
        return "device_not_found"
    return None


def _can_connect_bluetooth(
    mac: str, channel: int, timeout: float
) -> tuple[bool, str | None, int | None]:
    """Probe RFCOMM connectivity to a paired Bluetooth printer.

    Returns ``(success, error_code, errno)``. On success error_code/errno are None.
    """
    # Cap probe timeout so a missing printer can't burn the user's full
    # configured timeout in the config flow.
    probe_timeout = min(timeout, 5.0)
    try:
        transport = bluetooth_transport.open_rfcomm_transport(mac, channel, probe_timeout)
    except OSError as exc:
        err_no = getattr(exc, "errno", None)
        code = _classify_bt_error(exc)
        if code is None:
            _LOGGER.debug(
                "Bluetooth connection probe failed for %s ch=%s (errno=%s): %s",
                mac,
                channel,
                err_no,
                sanitize_log_message(str(exc)),
            )
        return False, code, err_no
    else:
        with contextlib.suppress(Exception):
            transport.close()
        return True, None, None


async def _list_paired_bluetooth_devices() -> list[dict[str, Any]]:
    """Wrapper for backwards compatibility — see :func:`bluez.list_paired_bluetooth_devices`."""
    return await list_paired_bluetooth_devices()


def _build_bt_device_choices(
    devices: list[dict[str, Any]], *, imaging_only: bool = True
) -> dict[str, str]:
    """Build the dropdown for the bluetooth_select step.

    Filters to imaging-class devices by default so users see only their
    printer rather than every paired phone/headset on the host. Some cheap
    printers don't advertise the class — when no imaging devices are found
    the caller falls back to ``imaging_only=False`` to show everything.

    Always offers a manual-entry fallback so users without bluez D-Bus
    access can still configure paired devices.
    """
    candidates = (
        [d for d in devices if d.get("is_imaging")] if imaging_only else list(devices)
    )
    choices: dict[str, str] = {d["_choice_key"]: d["label"] for d in candidates}
    # Surface "Show all" only when filtering imaging-only AND there's something
    # the user can't currently see (avoids redundant choice when no filter is in
    # effect or when nothing is hidden).
    if imaging_only and len(candidates) < len(devices):
        choices[BT_SHOW_ALL_KEY] = "Show all paired Bluetooth devices..."
    choices[BT_MANUAL_ENTRY_KEY] = "Manual MAC entry..."
    return choices
