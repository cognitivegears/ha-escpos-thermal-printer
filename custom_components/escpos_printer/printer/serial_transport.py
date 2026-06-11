"""Serial transport seam for serial/UART ESC/POS printers.

This module exposes:

* ``SerialTransport`` — Protocol with ``write(bytes)`` and ``close()``.
* ``open_serial_transport`` — factory function used by the adapter and the
  config-flow probe (``_can_connect_serial``). Accepts both filesystem paths
  (``/dev/ttyUSB0``, ``COM3``) and serialx URLs (``esphome://host:port``,
  ``rfc2217://host:port``, ``socket://host:port``).
"""

from __future__ import annotations

import contextlib
from typing import Any, Protocol


class SerialTransport(Protocol):
    """Minimal byte-sink interface used by ``SerialEscpos``."""

    def write(self, data: bytes) -> None:
        """Write bytes to the underlying transport."""

    def close(self) -> None:
        """Close the underlying transport."""


class _SerialTransportImpl:
    """Concrete byte-sink wrapping a connected ``serialx`` serial port."""

    def __init__(self, port: Any) -> None:
        self._port: Any = port

    def write(self, data: bytes) -> None:
        if not data:
            return
        self._port.write(data)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._port.close()


def open_serial_transport(
    port_or_url: str,
    baudrate: int,
    timeout: float,
) -> SerialTransport:
    """Open a serial transport for the given port path or URL.

    Accepts filesystem paths (``/dev/ttyUSB0``, ``COM3``) and serialx URL
    schemes (``esphome://``, ``rfc2217://``, ``socket://``). The ``baudrate``
    argument is passed through for direct serial connections; URL-based
    backends (e.g. ESPHome serial proxy) silently ignore it.

    Raises ``OSError`` on failure; the caller maps errno to user-facing error
    keys.
    """
    import serialx  # noqa: PLC0415

    port = serialx.serial_for_url(
        port_or_url,
        baudrate=baudrate,
        read_timeout=max(timeout, 0.1),
    )
    return _SerialTransportImpl(port)
