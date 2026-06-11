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
import time
from typing import Any, Protocol


class SerialTransport(Protocol):
    """Minimal byte-sink interface used by ``SerialEscpos``."""

    def write(self, data: bytes) -> None:
        """Write bytes to the underlying transport."""

    def close(self) -> None:
        """Close the underlying transport."""


class _SerialTransportImpl:
    """Concrete byte-sink wrapping a connected ``serialx`` serial port.

    All ``write()`` calls are coalesced into an internal buffer and sent to
    the port in a single ``_flush()`` call when ``close()`` is invoked.
    This avoids the rapid-fire burst of tiny writes that python-escpos
    generates (one per ESC/POS attribute: bold, align, text, cut …), which
    can overrun the receive buffer on resource-constrained serial proxies
    such as an ESP32 running the ESPHome serial-proxy component.

    ``write_chunk_size`` controls how the coalesced payload is split during
    flush; ``write_chunk_delay_s`` adds a pause between consecutive chunks.
    Both default to 0, meaning the buffered payload is sent as a single
    ``port.write()`` call.
    """

    def __init__(
        self,
        port: Any,
        write_chunk_size: int = 0,
        write_chunk_delay_s: float = 0.0,
    ) -> None:
        self._port: Any = port
        self._write_chunk_size = write_chunk_size
        self._write_chunk_delay_s = write_chunk_delay_s
        self._buffer = bytearray()

    def write(self, data: bytes) -> None:
        if data:
            self._buffer.extend(data)

    def _flush(self) -> None:
        if not self._buffer:
            return
        data = bytes(self._buffer)
        self._buffer.clear()
        if self._write_chunk_size <= 0 or len(data) <= self._write_chunk_size:
            self._port.write(data)
            return
        # Send in chunks with inter-chunk delays. Runs on an executor thread
        # so time.sleep is safe.
        for i in range(0, len(data), self._write_chunk_size):
            chunk = data[i : i + self._write_chunk_size]
            self._port.write(chunk)
            if self._write_chunk_delay_s > 0 and i + self._write_chunk_size < len(data):
                time.sleep(self._write_chunk_delay_s)

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._flush()
        with contextlib.suppress(Exception):
            self._port.close()


def open_serial_transport(
    port_or_url: str,
    baudrate: int,
    timeout: float,
    write_chunk_size: int = 0,
    write_chunk_delay_ms: int = 0,
) -> SerialTransport:
    """Open a serial transport for the given port path or URL.

    Accepts filesystem paths (``/dev/ttyUSB0``, ``COM3``) and serialx URL
    schemes (``esphome://``, ``rfc2217://``, ``socket://``). The ``baudrate``
    argument is passed through for direct serial connections; URL-based
    backends (e.g. ESPHome serial proxy) silently ignore it.

    All writes are buffered and flushed as a single payload when the
    transport is closed, coalescing the many small ``_raw()`` calls that
    python-escpos makes into one burst.  ``write_chunk_size`` splits that
    payload into smaller chunks; ``write_chunk_delay_ms`` adds a pause
    between consecutive chunks.  Both default to 0 (no chunking).

    Raises ``OSError`` on failure; the caller maps errno to user-facing error
    keys.
    """
    import serialx  # noqa: PLC0415

    port = serialx.serial_for_url(
        port_or_url,
        baudrate=baudrate,
        read_timeout=max(timeout, 0.1),
    )
    # serialx does not auto-open on construction (unlike pyserial); _fileno
    # remains None until open() is called, causing AssertionError on write().
    port.open()
    return _SerialTransportImpl(
        port,
        write_chunk_size=write_chunk_size,
        write_chunk_delay_s=write_chunk_delay_ms / 1000.0,
    )
