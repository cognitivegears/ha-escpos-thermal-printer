"""Control operation mixins for ESC/POS printer adapters."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from escpos.constants import GS

from ..security import (
    MAX_BEEP_DURATION,
    MAX_BEEP_TIMES,
    MAX_FEED_LINES,
    validate_numeric_input,
)
from .mapping_utils import map_cut

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class ControlOperationsMixin:
    """Mixin providing feed, cut, and beep methods."""

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

    async def _acquire_printer_or_offline(self, hass: Any) -> tuple[Any, bool]:
        """``_acquire_printer``, marking the adapter offline on connect failure."""
        raise NotImplementedError

    async def _release_printer(
        self, hass: Any, printer: Any, *, owned: bool, failed: bool = False
    ) -> None:
        """Close a printer instance if owned by the caller."""
        raise NotImplementedError

    async def _mark_success(self) -> None:
        """Mark a successful operation (implemented in base)."""
        raise NotImplementedError

    async def feed(self, hass: HomeAssistant, *, lines: int) -> None:
        """Feed paper by a number of lines."""
        try:
            lines_int = int(lines)
        except Exception:
            lines_int = 1
        lines_int = max(lines_int, 1)
        lines_int = min(lines_int, MAX_FEED_LINES)
        _LOGGER.debug("Feeding %s lines", lines_int)

        def _feed_inner(printer: Any) -> None:
            if hasattr(printer, "control"):
                try:
                    for _ in range(lines_int):
                        printer.control("LF")
                except Exception:
                    pass  # Fall through to other methods
                else:
                    return
            if hasattr(printer, "ln"):
                printer.ln(lines_int)
            else:
                try:
                    printer._raw(b"\n" * lines_int)
                except Exception:
                    for _ in range(lines_int):
                        printer.text("\n")

        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                await hass.async_add_executor_job(_feed_inner, printer)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()

    async def cut(self, hass: HomeAssistant, *, mode: str, feed_before_cut: bool = True) -> None:
        """Cut the paper.

        ``feed_before_cut`` maps to python-escpos's ``cut(feed=...)``, which
        force-feeds ~6 lines before cutting when true (its default). Default
        true here preserves that behaviour for existing callers.

        When ``feed_before_cut`` is false, python-escpos's own
        ``cut(feed=False)`` always emits the partial-cut opcode
        (``GS V 66 0``) regardless of ``mode`` (see
        ``escpos.escpos.Escpos.cut``) -- so that case is handled here by
        emitting the ESC/POS function-B opcode directly: ``GS V 65 0`` for
        full, ``GS V 66 0`` for partial (n=0 => no feed lines).
        """
        cut_mode = map_cut(mode)
        if not cut_mode:
            _LOGGER.warning("Invalid cut mode '%s', defaulting to full", mode)
            cut_mode = "FULL"

        def _cut_inner(printer: Any) -> None:
            if feed_before_cut:
                printer.cut(mode=cut_mode, feed=True)
            else:
                opcode = 65 if cut_mode == "FULL" else 66
                printer._raw(GS + b"V" + bytes([opcode]) + b"\x00")

        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                await hass.async_add_executor_job(_cut_inner, printer)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()

    async def beep(self, hass: HomeAssistant, *, times: int = 2, duration: int = 4) -> None:
        """Trigger the printer buzzer."""
        times_v = validate_numeric_input(times, 1, MAX_BEEP_TIMES, "times")
        # B-L2: ``duration`` and ``times`` are semantically distinct fields
        # — bound via the dedicated ``MAX_BEEP_DURATION`` constant even
        # though both happen to be 10 today.
        duration_v = validate_numeric_input(duration, 1, MAX_BEEP_DURATION, "duration")

        def _beep_inner(printer: Any) -> None:
            _LOGGER.debug("beep begin: times=%s duration=%s", times_v, duration_v)
            try:
                if hasattr(printer, "buzzer"):
                    printer.buzzer(times_v, duration_v)
                elif hasattr(printer, "beep"):
                    printer.beep(times_v, duration_v)
                else:
                    _LOGGER.warning("Printer does not support buzzer")
                    return
            except AttributeError:
                # Some python-escpos builds expose ``buzzer``/``beep`` as an
                # attribute that raises AttributeError deeper in the call
                # (e.g. delegating to a capability the transport lacks) --
                # treat that the same as "unsupported". Anything else (a
                # real transport failure) propagates so the normal
                # failed=True path below invalidates the connection and
                # flips the connectivity sensor offline.
                _LOGGER.warning("Printer does not support buzzer")

        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                await hass.async_add_executor_job(_beep_inner, printer)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()
