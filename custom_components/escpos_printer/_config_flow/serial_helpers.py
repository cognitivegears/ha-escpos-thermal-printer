"""Serial port discovery and connectivity helpers for config flow."""

from __future__ import annotations

import contextlib
import errno
import logging

from ..printer import serial_transport
from ..security import sanitize_log_message

_LOGGER = logging.getLogger(__name__)


# errno -> error_code, evaluated first; substring matching only when errno is None.
_SERIAL_ERRNO_TO_CODE: dict[int, str] = {
    errno.EACCES: "serial_permission_denied",
    errno.EPERM: "serial_permission_denied",
    errno.ENOENT: "serial_port_not_found",
    errno.ENODEV: "serial_port_not_found",
    errno.EBUSY: "serial_port_busy",
}


def _classify_serial_error(exc: Exception) -> str | None:
    """Map an exception from serial open to a stable error code.

    Returns ``None`` if the error doesn't match any recognized pattern; the
    caller surfaces that as the generic ``cannot_connect_serial`` key.
    """
    err_no = getattr(exc, "errno", None)
    if err_no is not None and err_no in _SERIAL_ERRNO_TO_CODE:
        return _SERIAL_ERRNO_TO_CODE[err_no]
    text = str(exc).lower()
    if "permission" in text or "access denied" in text:
        return "serial_permission_denied"
    if "no such file" in text or "not found" in text or "does not exist" in text:
        return "serial_port_not_found"
    if "busy" in text or "resource unavailable" in text:
        return "serial_port_busy"
    return None


def _can_connect_serial(
    port_or_url: str, baudrate: int, timeout: float
) -> tuple[bool, str | None, int | None]:
    """Probe serial connectivity by briefly opening and closing the port.

    Returns ``(success, error_code, errno)``. On success error_code/errno are None.
    Works for both filesystem paths (``/dev/ttyUSB0``) and URL schemes
    (``esphome://``, ``rfc2217://``, ``socket://``).
    """
    probe_timeout = min(timeout, 5.0)
    try:
        transport = serial_transport.open_serial_transport(port_or_url, baudrate, probe_timeout)
    except Exception as exc:
        err_no = getattr(exc, "errno", None)
        code = _classify_serial_error(exc)
        if code is None:
            _LOGGER.debug(
                "Serial connection probe failed for %s (errno=%s): %s",
                sanitize_log_message(port_or_url),
                err_no,
                sanitize_log_message(str(exc)),
            )
        return False, code, err_no
    else:
        with contextlib.suppress(Exception):
            transport.close()
        return True, None, None


def _serial_error_to_key(error_code: str | None) -> str:
    """Convert a serial error code to a strings.json error key."""
    known = {
        "serial_permission_denied",
        "serial_port_not_found",
        "serial_port_busy",
    }
    if error_code in known:
        return error_code
    return "cannot_connect_serial"
