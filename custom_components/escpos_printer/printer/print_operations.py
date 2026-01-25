"""Print operation mixins for ESC/POS printer adapters."""

from __future__ import annotations

import contextlib
import io
import logging
from typing import TYPE_CHECKING, Any

import aiohttp
from PIL import Image

from ..const import DEFAULT_CUT
from ..security import (
    sanitize_log_message,
    validate_image_url,
    validate_local_image_path,
    validate_qr_data,
    validate_text_input,
)
from .mapping_utils import map_align, map_multiplier, map_underline

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)


class PrintOperationsMixin:
    """Mixin providing print_text, print_qr, and print_image methods."""

    # These attributes are expected from the base class
    _config: Any
    _keepalive: bool
    _printer: Any
    _lock: Any

    def _connect(self) -> Any:
        """Create and return a printer connection (abstract in base)."""
        raise NotImplementedError

    def _wrap_text(self, text: str) -> str:
        """Wrap text to configured line width (implemented in base)."""
        raise NotImplementedError

    async def _apply_cut_and_feed(
        self, hass: Any, printer: Any, cut: str | None, feed: int | None
    ) -> None:
        """Apply feed and cut operations (implemented in base)."""
        raise NotImplementedError

    async def _mark_success(self) -> None:
        """Mark a successful operation (implemented in base)."""
        raise NotImplementedError

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
        align_m = map_align(align)
        ul = map_underline(underline)
        wmult = map_multiplier(width)
        hmult = map_multiplier(height)
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

        align_m = map_align(align)

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
            # If resizing fails for any reason, continue with the original image
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
