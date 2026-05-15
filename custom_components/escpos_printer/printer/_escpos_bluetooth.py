"""python-escpos subclass that writes through an :class:`RfcommTransport`.

python-escpos ships ``Network``, ``Usb``, ``Serial``, and ``File`` printer
classes but no Bluetooth-aware variant. Rather than vendoring a fork, we
build a minimal subclass of ``escpos.escpos.Escpos`` that delegates the
abstract ``_raw`` byte-write to a swappable transport. The subclass is
constructed lazily on first use and cached at module scope (via
``functools.cache``) so each print operation does not pay the
class-creation cost.
"""

from __future__ import annotations

import functools
from typing import Any

from .bluetooth_transport import RfcommTransport


@functools.cache
def _get_bluetooth_escpos_cls() -> type[Any]:
    """Late-import ``escpos.escpos.Escpos`` and return a Bluetooth subclass.

    Late import keeps the integration loadable when python-escpos isn't yet
    available (HA startup ordering). Tests that swap the ``escpos.escpos``
    module call ``_get_bluetooth_escpos_cls.cache_clear()`` to invalidate.
    """
    from escpos.escpos import Escpos  # noqa: PLC0415

    class _BluetoothEscpos(Escpos):
        """python-escpos subclass that writes through an RFCOMM transport."""

        def __init__(self, transport: RfcommTransport, profile: Any | None) -> None:
            self._transport: RfcommTransport | None = transport
            super().__init__(profile=profile)

        def _raw(self, msg: bytes) -> None:
            if self._transport is None:
                raise OSError("Bluetooth transport already closed")
            self._transport.write(msg)

        def _read(self) -> bytes:
            # RFCOMM SPP is one-way for ESC/POS; status reads aren't supported.
            # Returning empty rather than raising keeps python-escpos paths that
            # opportunistically read (e.g., during init) from blowing up; the
            # adapter never triggers status-read paths in practice.
            return b""

        def close(self) -> None:
            if self._transport is not None:
                try:
                    self._transport.close()
                finally:
                    self._transport = None

    return _BluetoothEscpos


def make_bluetooth_escpos(
    transport: RfcommTransport, profile: Any | None = None
) -> Any:
    """Return a python-escpos printer wired to the given RFCOMM transport."""
    cls = _get_bluetooth_escpos_cls()
    return cls(transport, profile)
