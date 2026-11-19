"""Raster print jobs for Bluetooth LE printers."""

from __future__ import annotations

import logging
from struct import pack
from typing import TYPE_CHECKING, Any

from escpos.constants import QR_ECLEVEL_H, QR_ECLEVEL_L, QR_ECLEVEL_M, QR_ECLEVEL_Q
from escpos.escpos import Escpos
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from PIL import Image, ImageChops, ImageOps
import qrcode

from ..const import DOMAIN
from ..security import MAX_PROCESSED_HEIGHT, sanitize_log_message
from ..text_effects.font_render import render_text_image
from .base_adapter import EscposPrinterAdapterBase
from .ble_transport import BLE_ERRORS, BlePrinterMismatchError, open_ble_printer

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from ..capabilities.ble_profiles import BlePrinterProfile
    from .config import BluetoothPrinterConfig


_LOGGER = logging.getLogger(__name__)
_LINE_DOTS = 24
_QR_LEVELS: dict[int | str, int] = {
    QR_ECLEVEL_L: qrcode.constants.ERROR_CORRECT_L,
    QR_ECLEVEL_M: qrcode.constants.ERROR_CORRECT_M,
    QR_ECLEVEL_Q: qrcode.constants.ERROR_CORRECT_Q,
    QR_ECLEVEL_H: qrcode.constants.ERROR_CORRECT_H,
    "L": qrcode.constants.ERROR_CORRECT_L,
    "M": qrcode.constants.ERROR_CORRECT_M,
    "Q": qrcode.constants.ERROR_CORRECT_Q,
    "H": qrcode.constants.ERROR_CORRECT_H,
}


class BleRasterJob(Escpos):
    """Render standard print operations into one monochrome raster job."""

    def __init__(self, profile: BlePrinterProfile) -> None:
        super().__init__()
        self.width = profile.width
        self._max_rows = profile.label_rows or MAX_PROCESSED_HEIGHT
        self._is_label = bool(profile.label_rows)
        self._rows = 0
        self._pixels = bytearray()
        self._align = "left"
        self._text_style: dict[str, Any] = {}
        self.density: int | None = None
        self.feed_dots = 0

    def _raw(self, msg: bytes) -> None:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="ble_unsupported")

    def _dpi(self) -> int:
        return 203

    def charcode(self, code: str = "AUTO") -> None:
        """Text is rasterized from Unicode."""

    def set(self, **kwargs: Any) -> None:
        """Store text and alignment settings for the next operation."""
        self._align = kwargs.get("align", "left")
        self._text_style = kwargs
        if (density := kwargs.get("density")) is not None:
            self.density = min(2, max(0, round(density * 2 / 8)))

    def _add_rows(self, count: int) -> None:
        if self._rows + count > self._max_rows:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="ble_job_too_long",
                translation_placeholders={"rows": str(self._max_rows)},
            )
        self._rows += count

    def image(self, img_source: Image.Image, *, center: bool = False, **kwargs: Any) -> None:
        """Place an image on a full-width raster and pack pixels MSB-first."""
        if img_source.width > self.width:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="ble_image_too_wide",
                translation_placeholders={"width": str(self.width)},
            )
        self._flush_spacing()
        self._add_rows(img_source.height)
        left = self.width - img_source.width
        if center or self._align == "center":
            left //= 2
        elif self._align != "right":
            left = 0
        with Image.new("L", (self.width, img_source.height), 255) as canvas:
            with img_source.convert("L") as grayscale:
                canvas.paste(grayscale, (left, 0))
            with ImageOps.invert(canvas).convert("1", dither=Image.Dither.NONE) as packed:
                self._pixels.extend(packed.tobytes())

    def ln(self, count: int = 1) -> None:
        """Queue line spacing; trailing spacing uses the printer's paper feed."""
        self.feed_dots += _LINE_DOTS * count

    def control(self, ctl: str, count: int = 1, tab_size: int = 4) -> None:
        """Queue line feeds from the shared control service."""
        if ctl != "LF":
            self._raw(b"")
        self.ln(count)

    def _flush_spacing(self) -> None:
        if self.feed_dots:
            self._add_rows(self.feed_dots)
            self._pixels.extend(bytes(self.feed_dots * (self.width // 8)))
            self.feed_dots = 0

    def text(self, txt: str) -> None:
        """Rasterize styled Unicode text using the bundled print fonts."""
        if not txt:
            return
        style = self._text_style
        scale_x = style.get("width", 1)
        scale_y = style.get("height", 1)
        font_size = 16 if style.get("font") == "b" else 19
        text = txt.removesuffix("\n")
        self._flush_spacing()
        with render_text_image(
            text,
            font_size=font_size,
            max_width_px=self.width // scale_x,
            align=self._align,
        ) as rendered:
            bitmap = rendered.resize(
                (rendered.width * scale_x, rendered.height * scale_y), Image.Resampling.NEAREST
            )
        if style.get("bold"):
            bitmap = ImageChops.darker(bitmap, ImageChops.offset(bitmap, 1, 0))
        if underline := style.get("underline"):
            # Match the configured weight on the printed line, including spaces.
            line_height = round(bitmap.height / max(1, len(text.split("\n"))))
            for bottom in range(line_height, bitmap.height + 1, line_height):
                bitmap.paste(0, (0, bottom - underline, bitmap.width, bottom))
        if style.get("invert"):
            bitmap = ImageOps.invert(bitmap)
        self.image(bitmap)

    def qr(self, content: str, ec: int | str = QR_ECLEVEL_M, size: int = 3, **kwargs: Any) -> None:
        """Fit a QR code on the paper, keeping whole modules and a quiet zone."""
        code = qrcode.QRCode(box_size=1, border=4, error_correction=_QR_LEVELS[ec])
        code.add_data(content)
        code.make(fit=True)
        modules = code.modules_count + 2 * code.border
        if modules > self.width:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="ble_image_too_wide",
                translation_placeholders={"width": str(self.width)},
            )
        code.box_size = min(size, self.width // modules)
        self._flush_spacing()
        with code.make_image().get_image() as image:
            self.image(image)

    def barcode(self, code: str, bc: str, **kwargs: Any) -> None:
        """Use the software barcode renderer in python-escpos."""
        kwargs["force_software"] = True
        self._flush_spacing()
        super().barcode(code, bc, **kwargs)

    def raster(self) -> bytes:
        """Return a single GS v 0 image, or no image for a feed-only job."""
        if not self._rows:
            return b""
        return b"\x1dv0\x00" + pack("<HH", self.width // 8, self._rows) + self._pixels

    def paper_feed(self) -> int:
        """Return the trailing feed, allowing enough paper to tear a receipt."""
        if self._is_label:
            return 0
        return max(80 if self._rows else 0, self.feed_dots)


class BlePrinterAdapter(EscposPrinterAdapterBase):
    """Run shared print operations with raster rendering and async BLE I/O."""

    def __init__(self, config: BluetoothPrinterConfig, profile: BlePrinterProfile) -> None:
        super().__init__(config)
        self._mac = config.mac
        self._profile = profile

    def _connect(self) -> BleRasterJob:
        return BleRasterJob(self._profile)

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Use one BLE connection per job."""
        await super().start(hass, keepalive=False, status_interval=status_interval)

    def get_connection_info(self) -> str:
        """Return a connection description for diagnostics."""
        return f"BLE {self._mac}"

    def get_profile_pixel_width(self, hass: HomeAssistant | None = None) -> int:
        """Return the physical width of the BLE printer's printhead."""
        return self._profile.width

    async def _status_check(self, hass: HomeAssistant) -> None:
        async with self._probe_lock_or_skip() as acquired:
            if not acquired:
                return
            try:
                async with open_ble_printer(hass, self._mac, self.config.timeout):
                    pass
            except (*BLE_ERRORS, BlePrinterMismatchError) as err:
                now = dt_util.utcnow()
                self._last_check = self._last_error = now
                self._last_error_reason = sanitize_log_message(str(err)) or "BLE connection failed"
                self._notify_status_change(False)
            else:
                await self._mark_success()

    async def _apply_cut_and_feed(
        self, hass: HomeAssistant, printer: BleRasterJob, cut: str | None, feed: int | None
    ) -> None:
        await super()._apply_cut_and_feed(hass, printer, None, feed)

    async def _release_printer(
        self,
        hass: HomeAssistant,
        printer: BleRasterJob,
        *,
        owned: bool,
        failed: bool = False,
        notify_status: bool = True,
    ) -> None:
        """Send the rendered job only after all operations have succeeded."""
        raster = b"" if failed else printer.raster()
        if not failed and (raster or printer.feed_dots):
            try:
                async with open_ble_printer(hass, self._mac, self.config.timeout) as link:
                    await link.print_job(
                        self._profile, raster, printer.paper_feed(), printer.density
                    )
            except (HomeAssistantError, *BLE_ERRORS, BlePrinterMismatchError) as err:
                _LOGGER.debug("BLE printing failed: %s", sanitize_log_message(str(err)))
                await super()._release_printer(hass, printer, owned=owned, failed=True)
                if isinstance(err, HomeAssistantError):
                    raise
                raise HomeAssistantError(
                    translation_domain=DOMAIN, translation_key="ble_print_failed"
                ) from err
        await super()._release_printer(
            hass, printer, owned=owned, failed=failed, notify_status=False
        )

    async def cut(self, hass: HomeAssistant, *, mode: str, feed_before_cut: bool = True) -> None:
        """Report that this printer has no cutter."""
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="ble_unsupported")

    async def beep(self, hass: HomeAssistant, *, times: int = 2, duration: int = 4) -> None:
        """Report that this printer has no supported beep command."""
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="ble_unsupported")
