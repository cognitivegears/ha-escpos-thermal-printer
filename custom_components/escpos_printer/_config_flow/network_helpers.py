"""Network connectivity + shared validator helpers for config flow."""

from __future__ import annotations

from collections.abc import Mapping
import logging
import socket
from typing import Any

from homeassistant.const import CONF_HOST, CONF_PORT

from ..const import CONF_DETECTED_MODEL, DEFAULT_PORT

_LOGGER = logging.getLogger(__name__)


def make_network_entry_title(data: Mapping[str, Any]) -> str:
    """Auto-generated title for a network entry: model-based when detected."""
    host = data.get(CONF_HOST, "")
    port = data.get(CONF_PORT, DEFAULT_PORT)
    model = data.get(CONF_DETECTED_MODEL)
    return f"{model} ({host}:{port})" if model else f"{host}:{port}"


def is_auto_network_title(title: str, data: Mapping[str, Any]) -> bool:
    """True when ``title`` is one this integration generated from ``data``.

    The auto title is a pure function of stored entry data, so "has the
    user renamed this entry?" is answered by recomputing it -- no stored
    original-title field to keep in sync. The bare "host:port" form is
    always included: entries created before model-based titles carry it
    even when a detected model is stored alongside.
    """
    legacy = f"{data.get(CONF_HOST, '')}:{data.get(CONF_PORT, DEFAULT_PORT)}"
    return title in {legacy, make_network_entry_title(data)}


def validate_custom_line_width(value: Any) -> tuple[int | None, str | None]:
    """Validate a user-entered custom line width.

    Returns ``(width_int, error_code)`` — exactly one is non-None.
    Hoisted out of both ``settings_steps`` and ``options_flow`` so
    both flows share the same bounds check (M2).
    """
    try:
        width_int = int(value)
    except ValueError, TypeError:
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


# --- GS I (Transmit Printer ID) query -------------------------------------
#
# Epson network printers answer GS I 66/67 with the maker/model name framed
# as 0x5F <ascii> 0x00. Clones typically ignore the command entirely; the
# short read timeout turns that silence into a clean None. The commands are
# read-only: nothing is printed and no printer state changes.

_GS_I_MAKER = b"\x1d\x49\x42"  # GS I 66 -> maker name ("EPSON")
_GS_I_MODEL = b"\x1d\x49\x43"  # GS I 67 -> model name ("TM-T20II")
_ID_HEADER = 0x5F
_ID_MAX_LEN = 80
_ID_READ_TIMEOUT = 2.0
# Each recv() below resets the read timeout, so an unbounded drain would let
# a misbehaving/malicious device drip-feed one byte at a time and hold the
# connection (and an HA executor thread) open indefinitely. Cap total bytes
# drained; if the cap is hit the stream is abandoned as unrecoverable.
_ID_DRAIN_MAX = 4096


def _read_id_reply(sock: socket.socket) -> str | None:
    """Read one 0x5F...0x00 framed reply; None on timeout/garbage/empty."""
    data = bytearray()
    try:
        while len(data) < _ID_MAX_LEN:
            chunk = sock.recv(1)
            if not chunk or chunk == b"\x00":
                break
            data += chunk
        else:
            # Hit the length cap without a NUL terminator: bytes from this
            # oversized reply are still queued on the socket and would
            # desync the framing of the NEXT reply. Drain them (discarding)
            # until NUL/timeout/closed so the stream resyncs -- bounded by
            # _ID_DRAIN_MAX so a drip-fed stream can't hang this forever.
            drained = 0
            while drained < _ID_DRAIN_MAX:
                chunk = sock.recv(1)
                if not chunk or chunk == b"\x00":
                    break
                drained += 1
    except OSError:
        pass  # timeout mid-reply: fall through and parse what we have
    if not data or data[0] != _ID_HEADER:
        return None
    text = data[1:].decode("ascii", errors="ignore")
    # Drop C0 control/escape bytes an untrusted peer could stuff into the
    # reply; leading/trailing whitespace is stripped last so filtering
    # doesn't leave it exposed at the ends.
    text = "".join(c for c in text if c.isprintable()).strip()
    return text or None


def query_printer_id(host: str, port: int, timeout: float) -> dict[str, str] | None:
    """Best-effort printer identification via GS I over raw TCP.

    Returns {"manufacturer": ..., "model": ...} (either key may be
    absent), or None when nothing was identified. Never raises.
    """
    result: dict[str, str] = {}
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(_ID_READ_TIMEOUT)
            for key, command in (("manufacturer", _GS_I_MAKER), ("model", _GS_I_MODEL)):
                sock.sendall(command)
                value = _read_id_reply(sock)
                if value is None:
                    break  # no answer: don't wait out a second timeout
                result[key] = value
    except OSError:
        _LOGGER.debug("GS I query failed for %s:%s", host, port)
    return result or None
