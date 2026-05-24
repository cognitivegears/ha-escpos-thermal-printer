"""Network connectivity + shared validator helpers for config flow."""

from __future__ import annotations

import logging
import socket
from typing import Any

_LOGGER = logging.getLogger(__name__)


def validate_custom_line_width(value: Any) -> tuple[int | None, str | None]:
    """Validate a user-entered custom line width.

    Returns ``(width_int, error_code)`` — exactly one is non-None.
    Hoisted out of both ``settings_steps`` and ``options_flow`` so
    both flows share the same bounds check (M2).
    """
    try:
        width_int = int(value)
    except (ValueError, TypeError):
        _LOGGER.warning("Invalid line width (not a number): %s", value)
        return None, "invalid_line_width"
    if width_int < 1 or width_int > 255:
        _LOGGER.warning("Invalid line width (out of range): %s", value)
        return None, "invalid_line_width"
    return width_int, None


def _can_connect(host: str, port: int, timeout: float) -> bool:
    """Test TCP connectivity to a host and port.

    Args:
        host: Hostname or IP address to connect to
        port: Port number to connect to
        timeout: Connection timeout in seconds

    Returns:
        True if connection succeeds, False otherwise
    """
    try:
        # Using a raw socket here to validate TCP reachability
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
