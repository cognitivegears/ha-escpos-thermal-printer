"""Shared host Protocol for printer-operation mixins.

The mixin families in this subpackage (``PrintOperationsMixin``,
``ImageOperationsMixin``, ``BarcodeOperationsMixin``,
``ControlOperationsMixin``) all need the same surface from ``self``:
the underlying connection, the per-adapter lock, the cut/feed apply
helper, etc. ``_PrinterHost`` is that contract.

B-M4: the Protocol used to live in ``print_operations.py`` and was
imported sideways by the other three mixin modules. Moving it here
puts the "what every mixin needs from its host" declaration in a
file whose name matches the role.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .config import BasePrinterConfig


class _PrinterHost(Protocol):
    """The surface a printer-operation mixin requires from ``self``.

    Methods are implemented by :class:`EscposPrinterAdapterBase`. The
    Protocol lets mypy verify the mixin contract without a runtime
    inheritance dependency.
    """

    _config: BasePrinterConfig
    _printer: Any
    _lock: asyncio.Lock

    # PEP 544 Protocol stubs. Docstring bodies keep the surface readable
    # without tripping CodeQL's ``py/ineffectual-statement`` rule (which
    # flags bare ``...`` placeholders).
    def _connect(self) -> Any:
        """Open the underlying transport and return the python-escpos object."""

    def _wrap_text(self, text: str) -> str:
        """Transcode ``text`` to the active codepage encoding."""

    def get_profile_pixel_width(self, hass: HomeAssistant | None = None) -> int | None:
        """Return the printer's pixel width per its profile, or ``None``."""

    async def _acquire_printer(self, hass: HomeAssistant) -> tuple[Any, bool]:
        """Acquire the underlying connection (returns ``(printer, owned)``)."""

    async def _release_printer(self, hass: HomeAssistant, printer: Any, *, owned: bool) -> None:
        """Release the connection acquired via :meth:`_acquire_printer`."""

    async def _apply_cut_and_feed(
        self,
        hass: HomeAssistant,
        printer: Any,
        cut: str | None,
        feed: int | None,
    ) -> None:
        """Apply the post-print cut + feed control sequence."""

    async def _mark_success(self) -> None:
        """Reset failure-count state after a successful operation."""


__all__ = ["_PrinterHost"]
