"""Base adapter class for ESC/POS printers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Callable
import contextlib
import logging
import textwrap
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import (
    MAX_FEED_LINES,
    sanitize_log_message,
    validate_numeric_input,
    validate_timeout,
)
from .barcode_operations import BarcodeOperationsMixin
from .config import BasePrinterConfig
from .control_operations import ControlOperationsMixin
from .mapping_utils import map_align, map_cut, map_multiplier, map_underline
from .print_operations import PrintOperationsMixin

_LOGGER = logging.getLogger(__name__)


# Late import of python-escpos to avoid import errors at HA startup if deps pending
def _get_network_printer() -> type[Any]:
    from escpos.printer import Network  # noqa: PLC0415

    return Network  # type: ignore[no-any-return]


def _get_usb_printer() -> type[Any]:
    from escpos.printer import Usb  # noqa: PLC0415

    return Usb  # type: ignore[no-any-return]


class EscposPrinterAdapterBase(
    PrintOperationsMixin,
    BarcodeOperationsMixin,
    ControlOperationsMixin,
    ABC,
):
    """Abstract base class for ESC/POS printer adapters."""

    def __init__(self, config: BasePrinterConfig) -> None:
        self._config: BasePrinterConfig = config
        # Validate timeout eagerly
        self._config.timeout = validate_timeout(self._config.timeout)
        self._keepalive: bool = False
        self._status_interval: int = 0
        self._printer: Any = None
        self._lock = asyncio.Lock()
        self._cancel_status: Callable[[], None] | None = None
        self._status: bool | None = None
        self._status_listeners: list[Callable[[bool], None]] = []
        self._last_check: Any = None
        self._last_ok: Any = None
        self._last_error: Any = None
        self._last_latency_ms: int | None = None
        self._last_error_reason: str | None = None
        self._last_error_errno: int | None = None

    @property
    def config(self) -> BasePrinterConfig:
        """Return the printer configuration."""
        return self._config

    @abstractmethod
    def _connect(self) -> Any:
        """Create and return a printer connection."""

    @abstractmethod
    async def _status_check(self, hass: HomeAssistant) -> None:
        """Perform a status check for the printer."""

    @abstractmethod
    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Start the adapter with optional keepalive and status checking."""
        self._keepalive = bool(keepalive)
        self._status_interval = max(0, int(status_interval))

        # Establish initial connection if keeping alive
        if self._keepalive and self._printer is None:
            def _mk() -> Any:
                return self._connect()

            self._printer = await hass.async_add_executor_job(_mk)

        # Schedule status checks
        if self._status_interval > 0:
            from datetime import timedelta  # noqa: PLC0415

            from homeassistant.helpers.event import async_track_time_interval  # noqa: PLC0415

            async def _tick(now: Any) -> None:
                await self._status_check(hass)

            self._cancel_status = async_track_time_interval(hass, _tick, timedelta(seconds=self._status_interval))
        # Perform an initial status probe only when status checks are enabled
        if self._status_interval > 0:
            await self._status_check(hass)

    async def stop(self) -> None:
        """Stop the adapter and clean up resources."""
        if self._cancel_status:
            self._cancel_status()
        self._cancel_status = None
        if self._printer is not None:
            with contextlib.suppress(Exception):
                self._printer.close()
            self._printer = None

    def get_status(self) -> bool | None:
        """Return the current printer status."""
        return self._status

    async def async_request_status_check(self, hass: HomeAssistant) -> None:
        """Request an immediate status check."""
        await self._status_check(hass)

    def add_status_listener(self, callback: Callable[[bool], None]) -> Callable[[], None]:
        """Add a status change listener and return an unsubscribe function."""
        self._status_listeners.append(callback)

        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._status_listeners.remove(callback)

        return _remove

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information about the adapter."""
        def _iso(dt_obj: Any) -> str | None:
            return dt_obj.isoformat() if dt_obj is not None else None

        return {
            "last_check": _iso(self._last_check),
            "last_ok": _iso(self._last_ok),
            "last_error": _iso(self._last_error),
            "last_latency_ms": self._last_latency_ms,
            "last_error_reason": self._last_error_reason,
            "last_error_errno": self._last_error_errno,
        }

    async def _acquire_printer(self, hass: HomeAssistant) -> tuple[Any, bool]:
        """Return a printer instance and whether it should be closed by the caller."""
        if self._keepalive and self._printer is not None:
            return self._printer, False
        printer = await hass.async_add_executor_job(self._connect)
        return printer, True

    async def _release_printer(self, hass: HomeAssistant, printer: Any, *, owned: bool) -> None:
        """Close a printer instance if owned by the caller."""
        if not owned:
            return

        def _close() -> None:
            with contextlib.suppress(Exception):
                printer.close()

        await hass.async_add_executor_job(_close)

    def _notify_status_change(self, ok: bool) -> None:
        """Notify all status listeners of a status change."""
        if self._status != ok:
            self._status = ok
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def _wrap_text(self, text: str) -> str:
        """Wrap text to the configured line width."""
        cols = max(0, int(self._config.line_width or 0))
        if cols <= 0:
            return text
        wrapped_lines: list[str] = []
        for line in text.splitlines():
            # Preserve empty lines
            if not line:
                wrapped_lines.append("")
                continue
            wrapped_lines.extend(textwrap.wrap(line, width=cols, replace_whitespace=False, drop_whitespace=False))
        return "\n".join(wrapped_lines)

    # Static methods delegated to mapping_utils for backward compatibility
    @staticmethod
    def _map_align(align: str | None) -> str:
        """Map alignment string to escpos alignment value."""
        return map_align(align)

    @staticmethod
    def _map_underline(underline: str | None) -> int:
        """Map underline string to escpos underline value."""
        return map_underline(underline)

    @staticmethod
    def _map_multiplier(val: str | None) -> int:
        """Map multiplier string to escpos multiplier value."""
        return map_multiplier(val)

    @staticmethod
    def _map_cut(mode: str | None) -> str | None:
        """Map cut mode string to escpos cut value."""
        return map_cut(mode)

    def _get_profile_obj(self) -> Any:
        """Get the escpos profile object for this configuration."""
        if self._config.profile:
            try:
                from escpos import profile as escpos_profile  # noqa: PLC0415

                return escpos_profile.get_profile(self._config.profile)
            except Exception as e:
                _LOGGER.debug("Unknown printer profile '%s': %s", self._config.profile, sanitize_log_message(str(e)))
        return None

    async def _apply_cut_and_feed(self, hass: HomeAssistant, printer: Any, cut: str | None, feed: int | None) -> None:
        """Apply feed and cut operations to the printer."""
        # feed first, then cut
        if feed is not None:
            lines = validate_numeric_input(feed, 0, MAX_FEED_LINES, "feed")
            if lines > 0:
                def _feed() -> None:
                    # Some versions have ln(); otherwise send newlines
                    if hasattr(printer, "ln"):
                        printer.ln(lines)
                    else:
                        try:
                            printer._raw(b"\n" * lines)
                        except Exception:
                            for _ in range(lines):
                                printer.text("\n")

                await hass.async_add_executor_job(_feed)

        cut_mode = self._map_cut(cut)
        if cut_mode:
            def _cut() -> None:
                try:
                    printer.cut(mode=cut_mode)
                except Exception as e:
                    _LOGGER.debug("Cut not supported: %s", e)

            await hass.async_add_executor_job(_cut)

    async def _mark_success(self) -> None:
        """Mark a successful operation (updates status tracking)."""
        now = dt_util.utcnow()
        self._status = True
        self._last_ok = now
        self._last_check = now
        self._last_error_errno = None
        for cb in list(self._status_listeners):
            with contextlib.suppress(Exception):
                cb(True)
