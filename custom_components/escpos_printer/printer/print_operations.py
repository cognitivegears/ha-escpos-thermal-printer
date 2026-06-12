"""Print operation mixins for ESC/POS printer adapters (text + QR)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..const import DEFAULT_CUT
from ..security import (
    sanitize_log_message,
    validate_qr_data,
    validate_text_input,
)
from ._host import _PrinterHost
from .mapping_utils import map_align, map_multiplier, map_underline

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Re-exported for backward compat (B-M4 moved the canonical declaration
# into ``_host.py`` so all four mixin families import the contract from
# its file of record). Tests + adapters that already pulled from here
# keep working.
__all__ = ["PrintOperationsMixin", "_PrinterHost"]


class PrintOperationsMixin:
    """Mixin providing :meth:`print_text` and :meth:`print_qr`."""

    async def print_text(
        self: _PrinterHost,
        hass: HomeAssistant,
        *,
        text: str,
        align: str | None = None,
        bold: bool | None = None,
        underline: str | None = None,
        width: str | int | None = None,
        height: str | int | None = None,
        encoding: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        """Print text to the printer."""
        async with self._lock:
            printer, owned = await self._acquire_printer(hass)
            failed = True
            try:
                await _print_text_under_lock(
                    self,
                    hass,
                    printer,
                    text=text,
                    align=align,
                    bold=bold,
                    underline=underline,
                    width=width,
                    height=height,
                    encoding=encoding,
                )
                await self._apply_cut_and_feed(hass, printer, cut, feed)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()

    async def print_qr(
        self: _PrinterHost,
        hass: HomeAssistant,
        *,
        data: str,
        size: int | None = None,
        ec: str | None = None,
        align: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        """Print a QR code to the printer."""
        data = validate_qr_data(data)
        align_m = map_align(align)
        qsize = int(size) if size is not None else 3
        qsize = max(1, min(16, qsize))
        qec = (ec or "M").upper()
        if qec not in ("L", "M", "Q", "H"):
            qec = "M"

        def _map_qr_ec(level: str) -> Any:
            try:
                from escpos import escpos as _esc  # noqa: PLC0415

                return {
                    "L": getattr(_esc, "QR_ECLEVEL_L", "L"),
                    "M": getattr(_esc, "QR_ECLEVEL_M", "M"),
                    "Q": getattr(_esc, "QR_ECLEVEL_Q", "Q"),
                    "H": getattr(_esc, "QR_ECLEVEL_H", "H"),
                }[level]
            except Exception:
                return level

        def _do_print(printer: Any) -> None:
            if hasattr(printer, "set"):
                printer.set(align=align_m, normal_textsize=True)
            printer.qr(data, size=qsize, ec=_map_qr_ec(qec))

        async with self._lock:
            printer, owned = await self._acquire_printer(hass)
            failed = True
            try:
                await hass.async_add_executor_job(_do_print, printer)
                await self._apply_cut_and_feed(hass, printer, cut, feed)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()


# ---------------------------------------------------------------------------
# Module-level helper: runs the text-print body assuming the lock is held
# and ``printer`` is already acquired. Used by both ``print_text`` and the
# ``print_text_with_image`` adapter method (which needs to keep the lock
# across two operations for atomicity).
# ---------------------------------------------------------------------------


async def _print_text_under_lock(
    host: _PrinterHost,
    hass: HomeAssistant,
    printer: Any,
    *,
    text: str,
    align: str | None,
    bold: bool | None,
    underline: str | None,
    width: str | int | None,
    height: str | int | None,
    encoding: str | None,
) -> None:
    """Execute the text-print body. ``host._lock`` must already be held."""
    text = validate_text_input(text)
    align_m = map_align(align)
    ul = map_underline(underline)
    wmult = map_multiplier(width)
    hmult = map_multiplier(height)
    text_to_print = host._wrap_text(text)
    codepage = host._config.codepage

    def _do_print(p: Any) -> None:
        if codepage:
            try:
                if hasattr(p, "charcode"):
                    p.charcode(codepage)
            except Exception as e:
                _LOGGER.debug("Codepage set failed: %s", sanitize_log_message(str(e)))

        if hasattr(p, "set"):
            use_custom_size = wmult > 1 or hmult > 1
            p.set(
                align=align_m,
                bold=bool(bold),
                underline=ul,
                width=wmult,
                height=hmult,
                custom_size=use_custom_size,
                normal_textsize=not use_custom_size,
            )

        if encoding:
            # ``encoding`` is a per-call codepage override. ``charcode``
            # both selects the codepage table on the printer *and* points
            # python-escpos's text encoder at the matching codec, so a
            # subsequent ``p.text`` encodes correctly. (The old path
            # called ``p._set_codepage`` — removed in python-escpos 3.x —
            # so the override was silently a no-op and printed mojibake.)
            try:
                if hasattr(p, "charcode"):
                    p.charcode(encoding)
            except Exception as e:
                _LOGGER.warning(
                    "Unsupported encoding/codepage override '%s': %s",
                    encoding,
                    sanitize_log_message(str(e)),
                )
        p.text(text_to_print)

    await hass.async_add_executor_job(_do_print, printer)
