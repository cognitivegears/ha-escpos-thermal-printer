"""Barcode operation mixin for ESC/POS printer adapters."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..const import DEFAULT_CUT
from ..security import (
    sanitize_log_message,
    validate_barcode_data,
    validate_numeric_input,
)
from .mapping_utils import map_align

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class BarcodeOperationsMixin:
    """Mixin providing print_barcode method."""

    # These attributes are expected from the base class
    _keepalive: bool
    _printer: Any
    _lock: Any

    def _connect(self) -> Any:
        """Create and return a printer connection (abstract in base)."""
        raise NotImplementedError

    async def _acquire_printer(self, hass: Any) -> tuple[Any, bool]:
        """Return a printer instance and whether it should be closed by the caller."""
        raise NotImplementedError

    async def _release_printer(self, hass: Any, printer: Any, *, owned: bool) -> None:
        """Close a printer instance if owned by the caller."""
        raise NotImplementedError

    async def _apply_cut_and_feed(
        self, hass: Any, printer: Any, cut: str | None, feed: int | None
    ) -> None:
        """Apply feed and cut operations (implemented in base)."""
        raise NotImplementedError

    async def print_barcode(
        self,
        hass: HomeAssistant,
        *,
        code: str,
        bc: str,
        height: int = 64,
        width: int = 3,
        pos: str = "BELOW",
        font: str = "A",
        align_ct: bool = True,
        check: bool = True,
        force_software: object | None = None,
        align: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        """Print a barcode to the printer."""
        v_code, v_bc = validate_barcode_data(code, bc)
        height_v = validate_numeric_input(height, 1, 255, "height")
        width_v = validate_numeric_input(width, 2, 6, "width")
        pos_v = (pos or "BELOW").upper()
        if pos_v not in ("ABOVE", "BELOW", "BOTH", "OFF"):
            pos_v = "BELOW"
        font_v = (font or "A").upper()
        if font_v not in ("A", "B"):
            font_v = "A"
        align_m = map_align(align)

        def _do_print(printer: Any) -> None:
            if hasattr(printer, "set"):
                printer.set(align=align_m)
            # Attempt to pass 'force_software' when provided; fall back if unsupported
            kwargs = {
                "height": height_v,
                "width": width_v,
                "pos": pos_v,
                "font": font_v,
                "align_ct": bool(align_ct),
                "check": bool(check),
            }
            if force_software is not None:
                kwargs["force_software"] = force_software

            try:
                printer.barcode(
                    v_code,
                    v_bc,
                    **kwargs,
                )
            except TypeError as e:
                # Older python-escpos may not accept force_software; retry without it
                if "force_software" in kwargs:
                    _LOGGER.debug("force_software unsupported; retrying without it: %s", sanitize_log_message(str(e)))
                    kwargs.pop("force_software", None)
                    printer.barcode(
                        v_code,
                        v_bc,
                        **kwargs,
                    )
                else:
                    raise

        async with self._lock:
            printer, owned = await self._acquire_printer(hass)
            try:
                await hass.async_add_executor_job(_do_print, printer)
                await self._apply_cut_and_feed(hass, printer, cut, feed)
            finally:
                await self._release_printer(hass, printer, owned=owned)
