"""RFCOMM transport seam for Bluetooth Classic printers.

The data plane for Bluetooth Classic / RFCOMM does not need bluez D-Bus
once the device is paired on the host. We open a raw AF_BLUETOOTH socket
and write ESC/POS bytes to it.

This module exposes:

* ``RfcommTransport`` — Protocol with ``write(bytes)`` and ``close()``.
* ``open_rfcomm_transport`` — factory function used by the adapter and the
  config-flow probe (``_can_connect_bluetooth``). Production opens a raw
  ``socket.AF_BLUETOOTH`` + ``socket.BTPROTO_RFCOMM`` socket; tests
  monkeypatch this to return a TCP-loopback variant pointed at the
  existing ``VirtualPrinter`` emulator. The transport is the public seam
  for both call sites — bumping its signature is a breaking change.
"""

from __future__ import annotations

import contextlib
import socket
from typing import Protocol


class RfcommTransport(Protocol):
    """Minimal byte-sink interface used by ``BluetoothEscpos``."""

    def write(self, data: bytes) -> None:
        """Write bytes to the underlying transport."""

    def close(self) -> None:
        """Close the underlying transport."""


class _SocketTransport:
    """Concrete byte-sink wrapping a connected ``socket.socket``."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    def write(self, data: bytes) -> None:
        if not data:
            return
        self._sock.sendall(data)

    def close(self) -> None:
        with contextlib.suppress(OSError):
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()


def _open_af_bluetooth_socket(mac: str, channel: int, timeout: float) -> socket.socket:
    """Open a connected AF_BLUETOOTH RFCOMM socket.

    Raises ``OSError`` on failure (caller maps to user-facing error keys).
    """
    af_bluetooth = getattr(socket, "AF_BLUETOOTH", None)
    btproto_rfcomm = getattr(socket, "BTPROTO_RFCOMM", None)
    if af_bluetooth is None or btproto_rfcomm is None:
        raise OSError(
            "AF_BLUETOOTH/BTPROTO_RFCOMM not available on this platform. "
            "Bluetooth Classic printers require Linux with kernel Bluetooth support."
        )

    sock = socket.socket(af_bluetooth, socket.SOCK_STREAM, btproto_rfcomm)
    try:
        sock.settimeout(max(timeout, 0.1))
        sock.connect((mac, channel))
    except OSError:
        with contextlib.suppress(OSError):
            sock.close()
        raise
    return sock


def open_rfcomm_transport(mac: str, channel: int, timeout: float) -> RfcommTransport:
    """Open an RFCOMM transport for the given paired device.

    This is the seam swapped by tests: production uses an ``AF_BLUETOOTH``
    socket; tests monkeypatch this function to return a TCP-loopback transport
    pointed at the ``VirtualPrinter`` emulator.
    """
    sock = _open_af_bluetooth_socket(mac, channel, timeout)
    return _SocketTransport(sock)
