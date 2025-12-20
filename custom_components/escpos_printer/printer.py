from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import io
import logging
import socket
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
def _get_network_printer() -> type[Any]:
    from escpos.printer import Network

    return Network  # type: ignore[no-any-return]


@dataclass
class PrinterConfig:
    host: str
    port: int = 9100
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

    # Utilities
    def _connect(self) -> Any:
        Network = _get_network_printer()
        profile_obj = None
        if self._config.profile:
            try:
                from escpos import profile as escpos_profile

                profile_obj = escpos_profile.get_profile(self._config.profile)
            except Exception as e:
                _LOGGER.debug("Unknown printer profile '%s': %s", self._config.profile, sanitize_log_message(str(e)))
                profile_obj = None
        return Network(
            self._config.host,
            port=self._config.port,
            timeout=self._config.timeout,
            profile=profile_obj,
        )

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
            from datetime import timedelta

            from homeassistant.helpers.event import async_track_time_interval

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
            try:
                self._printer.close()
            except Exception:
                pass
            self._printer = None

    async def _status_check(self, hass: HomeAssistant) -> None:
        # Non-invasive TCP reachability check
        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            try:
                with socket.create_connection((self._config.host, self._config.port), timeout=min(self._config.timeout, 3.0)):
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    return True, None, latency_ms
            except OSError as e:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return False, str(e), latency_ms

        ok, err, latency_ms = await hass.async_add_executor_job(_probe)
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "unreachable")
        if self._status != ok:
            self._status = ok
            if not ok:
                _LOGGER.warning("Printer %s:%s not reachable", self._config.host, self._config.port)
            # Notify listeners
            for cb in list(self._status_listeners):
                try:
                    cb(ok)
                except Exception:
                    pass

    def get_status(self) -> bool | None:
        return self._status

    async def async_request_status_check(self, hass: HomeAssistant) -> None:
        await self._status_check(hass)

    def add_status_listener(self, callback: Callable[[bool], None]) -> Callable[[], None]:
        self._status_listeners.append(callback)
        def _remove() -> None:
            try:
                self._status_listeners.remove(callback)
            except ValueError:
                pass
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
    async def print_text(
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

        def _do_print() -> None:
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
                    except Exception:
                        printer.text(text_to_print)
                else:
                    printer.text(text_to_print)
            finally:
                if not self._keepalive:
                    try:
                        printer.close()
                    except Exception:
                        pass

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    try:
                        printer_for_post.close()
                    except Exception:
                        pass
        # Successful operation implies reachable
        now = dt_util.utcnow()
        self._status = True
        self._last_ok = now
        self._last_check = now
        for cb in list(self._status_listeners):
            try:
                cb(True)
            except Exception:
                pass

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
                from escpos import escpos as _esc
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
                    try:
                        printer.close()
                    except Exception:
                        pass

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    try:
                        printer_for_post.close()
                    except Exception:
                        pass

    async def print_image(
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
                    try:
                        resp.close()
                    except Exception:
                        pass
            finally:
                try:
                    await session.close()
                except Exception:
                    pass
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
                    try:
                        printer.close()
                    except Exception:
                        pass

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    try:
                        printer_for_post.close()
                    except Exception:
                        pass

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
                        return
                    except Exception:
                        pass
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
                    try:
                        printer.close()
                    except Exception:
                        pass

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
                    try:
                        printer.close()
                    except Exception:
                        pass

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
                kwargs = dict(
                    height=height_v,
                    width=width_v,
                    pos=pos_v,
                    font=font_v,
                    align_ct=bool(align_ct),
                    check=bool(check),
                )
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
                    try:
                        printer.close()
                    except Exception:
                        pass

        async with self._lock:
            await hass.async_add_executor_job(_do_print)
            printer_for_post = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await self._apply_cut_and_feed(hass, printer_for_post, cut, feed)
            finally:
                if not self._keepalive:
                    try:
                        printer_for_post.close()
                    except Exception:
                        pass

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
                    try:
                        printer.close()
                    except Exception:
                        pass
