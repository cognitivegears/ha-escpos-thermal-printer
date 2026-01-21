from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import Callable
import contextlib
from dataclasses import dataclass, field
import io
import logging
import socket
import textwrap
import time
from typing import Any, Literal

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from PIL import Image

from .const import (
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_IN_EP,
    DEFAULT_OUT_EP,
)
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
    from escpos.printer import Network  # noqa: PLC0415

    return Network  # type: ignore[no-any-return]


def _get_usb_printer() -> type[Any]:
    from escpos.printer import Usb  # noqa: PLC0415

    return Usb  # type: ignore[no-any-return]


# Configuration dataclasses
@dataclass
class BasePrinterConfig:
    """Base printer configuration shared by all connection types."""

    codepage: str | None = None
    profile: str | None = None
    line_width: int = 48
    timeout: float = 4.0


@dataclass
class NetworkPrinterConfig(BasePrinterConfig):
    """Configuration for network (TCP/IP) printers."""

    connection_type: Literal["network"] = field(default="network", repr=False)
    host: str = ""
    port: int = 9100


@dataclass
class UsbPrinterConfig(BasePrinterConfig):
    """Configuration for USB printers."""

    connection_type: Literal["usb"] = field(default="usb", repr=False)
    vendor_id: int = 0
    product_id: int = 0
    in_ep: int = DEFAULT_IN_EP
    out_ep: int = DEFAULT_OUT_EP


# Type alias for config union (use for type hints)
PrinterConfigTypes = NetworkPrinterConfig | UsbPrinterConfig

# Backward-compatible alias: PrinterConfig(...) still works and creates NetworkPrinterConfig
# This maintains API compatibility for existing code that instantiates PrinterConfig directly
PrinterConfig = NetworkPrinterConfig


class EscposPrinterAdapterBase(ABC):
    """Abstract base class for ESC/POS printer adapters."""

    def __init__(self, config: BasePrinterConfig) -> None:
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
        }

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

    @staticmethod
    def _map_align(align: str | None) -> str:
        """Map alignment string to escpos alignment value."""
        if not align:
            return DEFAULT_ALIGN
        align = align.lower()
        return align if align in ("left", "center", "right") else DEFAULT_ALIGN

    @staticmethod
    def _map_underline(underline: str | None) -> int:
        """Map underline string to escpos underline value."""
        mapping = {"none": 0, "single": 1, "double": 2}
        if not underline:
            return 0
        return mapping.get(underline.lower(), 0)

    @staticmethod
    def _map_multiplier(val: str | None) -> int:
        """Map multiplier string to escpos multiplier value."""
        mapping = {"normal": 1, "double": 2, "triple": 3}
        if not val:
            return 1
        return mapping.get(val.lower(), 1)

    @staticmethod
    def _map_cut(mode: str | None) -> str | None:
        """Map cut mode string to escpos cut value."""
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
        for cb in list(self._status_listeners):
            with contextlib.suppress(Exception):
                cb(True)

    # Print operations
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
        """Print text to the printer."""
        text = validate_text_input(text)
        align_m = self._map_align(align)
        ul = self._map_underline(underline)
        wmult = self._map_multiplier(width)
        hmult = self._map_multiplier(height)
        text_to_print = self._wrap_text(text)

        def _do_print() -> None:  # noqa: PLR0912
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
        await self._mark_success()

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
        """Print a QR code to the printer."""
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
        """Print an image to the printer."""
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
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await hass.async_add_executor_job(_feed_inner, printer)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()

    async def cut(self, hass: HomeAssistant, *, mode: str) -> None:
        """Cut the paper."""
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
            printer = self._printer if self._keepalive and self._printer is not None else self._connect()
            try:
                await hass.async_add_executor_job(_beep_inner, printer)
            finally:
                if not self._keepalive:
                    with contextlib.suppress(Exception):
                        printer.close()


class NetworkPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for network (TCP/IP) ESC/POS printers."""

    def __init__(self, config: NetworkPrinterConfig) -> None:
        super().__init__(config)
        self._network_config = config

    @property
    def config(self) -> NetworkPrinterConfig:
        """Return the network printer configuration."""
        return self._network_config

    def _connect(self) -> Any:
        """Create and return a network printer connection."""
        network_class = _get_network_printer()
        profile_obj = self._get_profile_obj()
        return network_class(
            self._network_config.host,
            port=self._network_config.port,
            timeout=self._network_config.timeout,
            profile=profile_obj,
        )

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Non-invasive TCP reachability check for network printers."""
        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            try:
                with socket.create_connection((self._network_config.host, self._network_config.port), timeout=min(self._network_config.timeout, 3.0)):
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
                _LOGGER.warning("Printer %s:%s not reachable", self._network_config.host, self._network_config.port)
            # Notify listeners
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        return f"{self._network_config.host}:{self._network_config.port}"


class UsbPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for USB ESC/POS printers."""

    def __init__(self, config: UsbPrinterConfig) -> None:
        super().__init__(config)
        self._usb_config = config
        # USB printers don't support keepalive - reconnect per operation
        self._keepalive = False

    @property
    def config(self) -> UsbPrinterConfig:
        """Return the USB printer configuration."""
        return self._usb_config

    def _connect(self) -> Any:
        """Create and return a USB printer connection."""
        usb_class = _get_usb_printer()
        profile_obj = self._get_profile_obj()
        return usb_class(
            self._usb_config.vendor_id,
            self._usb_config.product_id,
            timeout=int(self._usb_config.timeout * 1000),  # USB timeout in milliseconds
            in_ep=self._usb_config.in_ep,
            out_ep=self._usb_config.out_ep,
            profile=profile_obj,
        )

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Check USB device availability via device enumeration."""
        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            try:
                import usb.core  # noqa: PLC0415

                device = usb.core.find(
                    idVendor=self._usb_config.vendor_id,
                    idProduct=self._usb_config.product_id,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
            except Exception as e:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return False, str(e), latency_ms
            else:
                if device is not None:
                    return True, None, latency_ms
                return False, "USB device not found", latency_ms

        ok, err, latency_ms = await hass.async_add_executor_job(_probe)
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "USB device unavailable")
        if self._status != ok:
            self._status = ok
            if not ok:
                _LOGGER.warning(
                    "USB Printer %04X:%04X not available",
                    self._usb_config.vendor_id,
                    self._usb_config.product_id,
                )
            # Notify listeners
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        return f"USB {self._usb_config.vendor_id:04X}:{self._usb_config.product_id:04X}"

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Start the adapter (USB ignores keepalive)."""
        # USB doesn't support persistent connections, override keepalive to False
        await super().start(hass, keepalive=False, status_interval=status_interval)


# Legacy alias for backward compatibility
EscposPrinterAdapter = NetworkPrinterAdapter


def create_printer_adapter(config: PrinterConfigTypes) -> EscposPrinterAdapterBase:
    """Factory function to create the appropriate printer adapter based on configuration."""
    if isinstance(config, UsbPrinterConfig):
        return UsbPrinterAdapter(config)
    return NetworkPrinterAdapter(config)
