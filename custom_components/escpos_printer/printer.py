from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass
import io
import logging
import textwrap
import time
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from PIL import Image

from .const import DEFAULT_ALIGN, DEFAULT_CUT
from .security import (
    MAX_BEEP_TIMES,
    MAX_FEED_LINES,
    sanitize_log_message,
    validate_barcode_data,
    validate_image_url,
    validate_local_image_path,
    validate_numeric_input,
    validate_qr_data,
    validate_text_input,
    validate_timeout,
)

_LOGGER = logging.getLogger(__name__)


# Late import of python-escpos to avoid import errors at HA startup if deps pending
def _get_cups_printer() -> type[Any]:
    from escpos.printer import CupsPrinter  # noqa: PLC0415

    return CupsPrinter  # type: ignore[no-any-return]


def _get_cups_connection(server: str | None = None) -> Any:
    """Get a CUPS connection, optionally to a remote server.

    Args:
        server: CUPS server address (e.g., 'hostname' or 'hostname:port').
                If None, connects to localhost.

    Returns:
        cups.Connection object.
    """
    import cups  # noqa: PLC0415

    if server:
        cups.setServer(server)
    return cups.Connection()


def is_cups_available(server: str | None = None) -> bool:
    """Check if CUPS is available on the system.

    Args:
        server: CUPS server address. If None, connects to localhost.

    Returns:
        True if CUPS/pycups is available, False otherwise.
    """
    try:
        import cups  # noqa: PLC0415

        _get_cups_connection(server)
        return True
    except ImportError:
        _LOGGER.warning("pycups library not available - CUPS printing disabled")
        return False
    except Exception as e:
        _LOGGER.warning("CUPS not available: %s", sanitize_log_message(str(e)))
        return False


def get_cups_printers(server: str | None = None) -> list[str]:
    """Get list of available CUPS printers.

    Args:
        server: CUPS server address. If None, connects to localhost.

    Returns:
        List of CUPS printer names.
    """
    try:
        conn = _get_cups_connection(server)
        printers = conn.getPrinters()
        return list(printers.keys())
    except ImportError:
        _LOGGER.warning("pycups library not available")
        return []
    except Exception as e:
        _LOGGER.warning("Failed to get CUPS printers: %s", sanitize_log_message(str(e)))
        return []


def is_cups_printer_available(printer_name: str, server: str | None = None) -> bool:
    """Check if a CUPS printer exists.

    Args:
        printer_name: Name of the CUPS printer to check.
        server: CUPS server address. If None, connects to localhost.

    Returns:
        True if printer exists, False otherwise.
    """
    try:
        conn = _get_cups_connection(server)
        printers = conn.getPrinters()
        return printer_name in printers
    except ImportError:
        _LOGGER.warning("pycups library not available")
        return False
    except Exception as e:
        _LOGGER.warning("Failed to check CUPS printer: %s", sanitize_log_message(str(e)))
        return False


def get_cups_printer_status(printer_name: str, server: str | None = None) -> tuple[bool, str | None]:
    """Get status of a CUPS printer.

    Args:
        printer_name: Name of the CUPS printer.
        server: CUPS server address. If None, connects to localhost.

    Returns:
        Tuple of (is_available, error_message).
    """
    try:
        import cups  # noqa: PLC0415
    except ImportError:
        return False, "pycups library not available"

    try:
        conn = _get_cups_connection(server)
        printers = conn.getPrinters()
        if printer_name not in printers:
            return False, "Printer not found"

        printer_info = printers[printer_name]
        # CUPS printer states: 3=idle, 4=processing, 5=stopped
        state = printer_info.get("printer-state", 0)
        state_reasons = printer_info.get("printer-state-reasons", [])

        if state == 5:  # Stopped
            reason = state_reasons[0] if state_reasons else "Printer stopped"
            return False, str(reason)

        # Check for error states in reasons
        if state_reasons and state_reasons != ["none"]:
            for reason in state_reasons:
                if "error" in str(reason).lower():
                    return False, str(reason)

        return True, None
    except Exception as e:
        return False, str(e)


@dataclass
class PrinterConfig:
    printer_name: str
    cups_server: str | None = None
    timeout: float = 4.0
    codepage: str | None = None
    profile: str | None = None
    line_width: int = 48


class EscposPrinterAdapter:
    def __init__(self, config: PrinterConfig) -> None:
        self._config = config
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

    @property
    def config(self) -> PrinterConfig:
        """Return the printer configuration."""
        return self._config

    # Utilities
    def _connect(self) -> Any:
        import cups  # noqa: PLC0415

        # Set the CUPS server if configured
        if self._config.cups_server:
            _LOGGER.debug("Setting CUPS server to: %s", self._config.cups_server)
            cups.setServer(self._config.cups_server)

        _LOGGER.debug("Connecting to CUPS printer: %s", self._config.printer_name)
        cups_class = _get_cups_printer()
        profile_obj = None
        if self._config.profile:
            try:
                from escpos import profile as escpos_profile  # noqa: PLC0415

                profile_obj = escpos_profile.get_profile(self._config.profile)
            except Exception as e:
                _LOGGER.debug("Unknown printer profile '%s': %s", self._config.profile, sanitize_log_message(str(e)))
                profile_obj = None

        printer = cups_class(
            self._config.printer_name,
            profile=profile_obj,
        )
        _LOGGER.debug("CUPS printer connection created: %s", printer)
        return printer

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
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
        if self._cancel_status:
            self._cancel_status()
        self._cancel_status = None
        if self._printer is not None:
            with contextlib.suppress(Exception):
                self._printer.close()
            self._printer = None

    async def _status_check(self, hass: HomeAssistant) -> None:
        # CUPS printer status check
        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            ok, err = get_cups_printer_status(self._config.printer_name, self._config.cups_server)
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ok, err, latency_ms

        ok, err, latency_ms = await hass.async_add_executor_job(_probe)
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "unavailable")
        if self._status != ok:
            self._status = ok
            if not ok:
                _LOGGER.warning("CUPS printer '%s' not available: %s", self._config.printer_name, err)
            # Notify listeners
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def get_status(self) -> bool | None:
        return self._status

    async def async_request_status_check(self, hass: HomeAssistant) -> None:
        await self._status_check(hass)

    def add_status_listener(self, callback: Callable[[bool], None]) -> Callable[[], None]:
        self._status_listeners.append(callback)
        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._status_listeners.remove(callback)
        return _remove

    def get_diagnostics(self) -> dict[str, Any]:
        def _iso(dt_obj: Any) -> str | None:
            return dt_obj.isoformat() if dt_obj is not None else None
        return {
            "last_check": _iso(self._last_check),
            "last_ok": _iso(self._last_ok),
            "last_error": _iso(self._last_error),
            "last_latency_ms": self._last_latency_ms,
            "last_error_reason": self._last_error_reason,
        }

    def _wrap_text(self, text: str) -> str:
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

    @staticmethod
    def _map_align(align: str | None) -> str:
        if not align:
            return DEFAULT_ALIGN
        align = align.lower()
        return align if align in ("left", "center", "right") else DEFAULT_ALIGN

    @staticmethod
    def _map_underline(underline: str | None) -> int:
        mapping = {"none": 0, "single": 1, "double": 2}
        if not underline:
            return 0
        return mapping.get(underline.lower(), 0)

    @staticmethod
    def _map_multiplier(val: str | None) -> int:
        mapping = {"normal": 1, "double": 2, "triple": 3}
        if not val:
            return 1
        return mapping.get(val.lower(), 1)

    @staticmethod
    def _map_cut(mode: str | None) -> str | None:
        if not mode:
            return None
        mode_l = mode.lower()
        if mode_l == "partial":
            return "PART"
        if mode_l == "full":
            return "FULL"
        if mode_l == "none":
            return None
        return None

    async def _apply_cut_and_feed(self, hass: HomeAssistant, printer: Any, cut: str | None, feed: int | None) -> None:
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

    # Operations
    async def print_text(  # noqa: PLR0915
        self,
        hass: HomeAssistant,
        *,
        text: str,
        align: str | None = None,
        bold: bool | None = None,
        underline: str | None = None,
        width: str | None = None,
        height: str | None = None,
        encoding: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        text = validate_text_input(text)
        align_m = self._map_align(align)
        ul = self._map_underline(underline)
        wmult = self._map_multiplier(width)
        hmult = self._map_multiplier(height)
        text_to_print = self._wrap_text(text)

        def _do_print() -> None:  # noqa: PLR0912
            _LOGGER.debug("print_text begin: text=%r, align=%s", text_to_print[:50] if len(text_to_print) > 50 else text_to_print, align_m)
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                # Optional codepage
                if self._config.codepage:
                    try:
                        if hasattr(printer, "charcode"):
                            printer.charcode(self._config.codepage)
                    except Exception as e:
                        _LOGGER.debug("Codepage set failed: %s", sanitize_log_message(str(e)))

                # Set style
                if hasattr(printer, "set"):
                    _LOGGER.debug("Setting printer style: align=%s, bold=%s", align_m, bold)
                    printer.set(align=align_m, bold=bool(bold), underline=ul, width=wmult, height=hmult)

                # Encoding is best-effort; python-escpos handles str internally.
                if encoding:
                    try:
                        # Try to set codepage if printer exposes helper
                        if hasattr(printer, "_set_codepage"):
                            try:
                                printer._set_codepage(encoding)
                            except Exception:
                                _LOGGER.warning("Unsupported encoding/codepage: %s", encoding)
                        text_bytes = text_to_print.encode(encoding, errors="replace")
                        if hasattr(printer, "_raw"):
                            printer._raw(text_bytes)
                        else:
                            printer.text(text_to_print)
                    except Exception as e:
                        _LOGGER.debug("Encoding error, falling back: %s", e)
                        printer.text(text_to_print)
                else:
                    _LOGGER.debug("Sending text to printer...")
                    printer.text(text_to_print)
                    _LOGGER.debug("Text sent successfully")
            except Exception as e:
                _LOGGER.error("print_text failed: %s", sanitize_log_message(str(e)))
                raise
            finally:
                if not self._keepalive:
                    _LOGGER.debug("Closing printer connection")
                    with contextlib.suppress(Exception):
                        printer.close()

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer_for_post.close()
        # Successful operation implies reachable
        now = dt_util.utcnow()
        self._status = True
        self._last_ok = now
        self._last_check = now
        for cb in list(self._status_listeners):
            with contextlib.suppress(Exception):
                cb(True)

    async def print_qr(
        self,
        hass: HomeAssistant,
        *,
        data: str,
        size: int | None = None,
        ec: str | None = None,
        align: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        data = validate_qr_data(data)
        align_m = self._map_align(align)
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

        def _do_print() -> None:
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                if hasattr(printer, "set"):
                    printer.set(align=align_m)
                printer.qr(data, size=qsize, ec=_map_qr_ec(qec))
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer_for_post.close()

    async def print_image(  # noqa: PLR0915
        self,
        hass: HomeAssistant,
        *,
        image: str,
        high_density: bool = True,
        align: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        # Resolve image source
        img_obj: Image.Image

        if image.lower().startswith(("http://", "https://")):
            _LOGGER.debug("Downloading image from URL: %s", sanitize_log_message(image, ["text", "data"]))
            url = validate_image_url(image)
            # Use a local ClientSession to avoid depending on HA http component in unit tests
            session = aiohttp.ClientSession()
            try:
                resp = await session.get(url)
                try:
                    resp.raise_for_status()
                    content = await resp.read()
                finally:
                    with contextlib.suppress(Exception):
                        resp.close()
            finally:
                with contextlib.suppress(Exception):
                    await session.close()
            img_obj = Image.open(io.BytesIO(content))
        else:
            _LOGGER.debug("Opening local image: %s", image)
            path = validate_local_image_path(image)
            img_obj = Image.open(path)

        align_m = self._map_align(align)

        # Resize overly wide images to a sane default (e.g., 512px)
        try:
            max_width = 512
            orig_w, orig_h = img_obj.width, img_obj.height
            if orig_w > max_width:
                ratio = max_width / float(orig_w)
                new_size = (max_width, int(orig_h * ratio))
                img_obj = img_obj.resize(new_size)
                _LOGGER.debug("Resized image from %sx%s to %sx%s", orig_w, orig_h, new_size[0], new_size[1])
        except Exception:
            pass

        def _do_print() -> None:
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                if hasattr(printer, "set"):
                    printer.set(align=align_m)
                # Some printers need conversion; python-escpos handles PIL.Image
                if hasattr(printer, "image"):
                    printer.image(img_obj, high_density_vertical=high_density, high_density_horizontal=high_density)
                else:
                    # Fallback: convert to bytes via ESC/POS raster if possible
                    printer.text("[image printing not supported by this printer]\n")
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer_for_post.close()

    async def feed(self, hass: HomeAssistant, *, lines: int) -> None:
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
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await hass.async_add_executor_job(_feed_inner, printer)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()

    async def cut(self, hass: HomeAssistant, *, mode: str) -> None:
        cut_mode = self._map_cut(mode)
        if not cut_mode:
            _LOGGER.warning("Invalid cut mode '%s', defaulting to full", mode)
            cut_mode = "FULL"
        async with self._lock:
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await hass.async_add_executor_job(lambda: printer.cut(mode=cut_mode))
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()

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
        v_code, v_bc = validate_barcode_data(code, bc)
        height_v = validate_numeric_input(height, 1, 255, "height")
        width_v = validate_numeric_input(width, 2, 6, "width")
        pos_v = (pos or "BELOW").upper()
        if pos_v not in ("ABOVE", "BELOW", "BOTH", "OFF"):
            pos_v = "BELOW"
        font_v = (font or "A").upper()
        if font_v not in ("A", "B"):
            font_v = "A"
        align_m = self._map_align(align)

        def _do_print() -> None:
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
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
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer_for_post.close()

    async def beep(self, hass: HomeAssistant, *, times: int = 2, duration: int = 4) -> None:
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
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await hass.async_add_executor_job(_beep_inner, printer)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()
