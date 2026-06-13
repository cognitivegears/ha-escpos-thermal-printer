"""python-escpos subclass that writes through a :class:`SerialTransport`.

python-escpos ships ``Network``, ``Usb``, ``Serial``, and ``File`` printer
classes, but its built-in ``Serial`` class hard-imports ``pyserial``.  We use
``serialx`` instead (for URL-based transports such as ESPHome serial proxies)
and therefore build a minimal subclass of ``escpos.escpos.Escpos`` that
delegates the abstract ``_raw`` byte-write to a swappable transport, mirroring
the Bluetooth adapter's ``_escpos_bluetooth`` approach.

The subclass is constructed lazily on first use and cached at module scope (via
``functools.cache``) so each print operation does not pay the class-creation
cost.
"""

from __future__ import annotations

import functools
from typing import Any

from .serial_transport import SerialTransport


@functools.cache
def _get_serial_escpos_cls() -> type[Any]:
    """Late-import ``escpos.escpos.Escpos`` and return a Serial subclass.

    Late import keeps the integration loadable when python-escpos isn't yet
    available (HA startup ordering). Tests that swap the ``escpos.escpos``
    module call ``_get_serial_escpos_cls.cache_clear()`` to invalidate.
    """
    from escpos.escpos import Escpos  # noqa: PLC0415

    class _SerialEscpos(Escpos):
        """python-escpos subclass that writes through a serial transport."""

        def __init__(self, transport: SerialTransport, profile: Any | None) -> None:
            self._transport: SerialTransport | None = transport
            super().__init__(profile=profile)

        def _raw(self, msg: bytes) -> None:
            if self._transport is None:
                raise OSError("Serial transport already closed")
            self._transport.write(msg)

        def _read(self) -> bytes:
            # ESC/POS serial connections are write-only in practice.
            # Returning empty keeps python-escpos paths that opportunistically
            # read (e.g., during init) from raising; the adapter never triggers
            # status-read paths.
            return b""

        def close(self) -> None:
            if self._transport is not None:
                try:
                    self._transport.close()
                finally:
                    self._transport = None

    return _SerialEscpos


def make_serial_escpos(transport: SerialTransport, profile: Any | None = None) -> Any:
    """Return a python-escpos printer wired to the given serial transport."""
    cls = _get_serial_escpos_cls()
    return cls(transport, profile)
