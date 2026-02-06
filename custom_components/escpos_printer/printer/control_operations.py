"""Control operation mixins for ESC/POS printer adapters."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..security import (
    MAX_BEEP_TIMES,
    MAX_FEED_LINES,
    sanitize_log_message,
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

    async def _release_printer(self, hass: Any, printer: Any, *, owned: bool) -> None:
        """Close a printer instance if owned by the caller."""
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
            printer, owned = await self._acquire_printer(hass)
            try:
                await hass.async_add_executor_job(_feed_inner, printer)
            finally:
                await self._release_printer(hass, printer, owned=owned)

    async def cut(self, hass: HomeAssistant, *, mode: str) -> None:
        """Cut the paper."""
        cut_mode = map_cut(mode)
        if not cut_mode:
            _LOGGER.warning("Invalid cut mode '%s', defaulting to full", mode)
            cut_mode = "FULL"
        async with self._lock:
            printer, owned = await self._acquire_printer(hass)
            try:
                await hass.async_add_executor_job(lambda: printer.cut(mode=cut_mode))
            finally:
                await self._release_printer(hass, printer, owned=owned)

    async def beep(self, hass: HomeAssistant, *, times: int = 2, duration: int = 4) -> None:
        """Trigger the printer buzzer."""
        times_v = validate_numeric_input(times, 1, MAX_BEEP_TIMES, "times")
        duration_v = validate_numeric_input(duration, 1, MAX_BEEP_TIMES, "duration")

        def _beep_inner(printer: Any) -> None:
            try:
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
                    _LOGGER.warning("Printer does not support buzzer")
            except Exception as e:
                _LOGGER.debug("Beep failed: %s", sanitize_log_message(str(e)))

        async with self._lock:
            printer, owned = await self._acquire_printer(hass)
            try:
                await hass.async_add_executor_job(_beep_inner, printer)
            finally:
                await self._release_printer(hass, printer, owned=owned)
