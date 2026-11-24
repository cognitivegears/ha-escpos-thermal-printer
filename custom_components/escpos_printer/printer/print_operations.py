"""Print operation mixins for ESC/POS printer adapters (text + QR)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from ..const import DEFAULT_CUT
from ..security import (
    MAX_LINE_HEIGHT,
    sanitize_log_message,
    validate_numeric_input,
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
        invert: bool | None = None,
        density: int | None = None,
        font: str | int | None = None,
        line_height: int | None = None,
        encoding: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
        wrap: bool = True,
    ) -> None:
        """Print text to the printer.

        ``wrap`` controls whether ``text`` is wrapped to the configured
        ``line_width`` before printing (the default, matching every
        existing caller). The calibration wizard's ruler step passes
        ``wrap=False`` so it can measure the *actual* printable width
        instead of always breaking at the width it's trying to measure.
        """
        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
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
                    invert=invert,
                    density=density,
                    font=font,
                    line_height=line_height,
                    encoding=encoding,
                    wrap=wrap,
                )
                await self._apply_cut_and_feed(hass, printer, cut, feed)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success(print_op=True)

    async def print_qr(
        self: _PrinterHost,
        hass: HomeAssistant,
        *,
        data: str,
        size: int | None = None,
        ec: str | None = None,
        align: str | None = None,
        native: bool = False,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
    ) -> None:
        """Print a QR code to the printer.

        ``native=True`` asks the printer to render the code itself
        (``GS ( k``) instead of sending a rasterised image; see
        :func:``_qr_under_lock`` for the fallback rules.
        """
        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                await _qr_under_lock(
                    hass,
                    printer,
                    data=data,
                    size=size,
                    ec=ec,
                    align=align,
                    native=native,
                    profile=self._config.profile,
                )
                await self._apply_cut_and_feed(hass, printer, cut, feed)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success(print_op=True)


async def _qr_under_lock(
    hass: HomeAssistant,
    printer: Any,
    *,
    data: str,
    size: int | None = None,
    ec: str | None = None,
    align: str | None = None,
    native: bool = False,
    profile: str | None = None,
) -> None:
    """Validate + print a QR on an already-acquired connection (lock held by caller).

    ``native=True`` renders the code on the printer (python-escpos
    ``qr(native=True)``, ESC/POS ``GS ( k``). Not every printer implements
    that command, so it falls back to the default image path when:

    - the configured printer profile declares no ``qrCode`` support, or
    - python-escpos raises while *building* the native command.

    The native command is built into a python-escpos ``Dummy`` buffer
    first and only then written to the transport in one ``_raw`` call, so
    a build failure is guaranteed to have sent no bytes (the image
    fallback can't double-print). A failure of the transport write itself
    is *not* retried as an image -- part of the command may already be on
    the wire -- and propagates like any other print failure.
    """
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

    # python-escpos QR_ECLEVEL_L/M/Q/H (escpos.constants); the native
    # command encodes the level as 48 + this value.
    native_ec = {"L": 0, "M": 1, "Q": 2, "H": 3}[qec]

    def _build_native() -> bytes | None:
        """Return the native QR command bytes, or None to use the image path."""
        from ..capabilities import profile_supports_feature  # noqa: PLC0415

        if not profile_supports_feature(profile, "qrCode"):
            _LOGGER.debug(
                "Profile %r declares no native QR support; using image rendering", profile
            )
            return None
        try:
            from escpos.printer import Dummy  # noqa: PLC0415

            buf = Dummy()
            buf.qr(data, size=qsize, ec=native_ec, native=True)
        except Exception as err:
            _LOGGER.warning(
                "Native QR rendering failed (%s); falling back to image rendering",
                sanitize_log_message(str(err)),
            )
            return None
        out: bytes = buf.output
        return out

    def _do_print(printer_obj: Any) -> None:
        if hasattr(printer_obj, "set"):
            printer_obj.set(align=align_m, normal_textsize=True, invert=False)
        if native:
            payload = _build_native()
            if payload is not None:
                printer_obj._raw(payload)
                return
        printer_obj.qr(data, size=qsize, ec=_map_qr_ec(qec))

    await hass.async_add_executor_job(_do_print, printer)


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
    invert: bool | None = None,
    density: int | None = None,
    font: str | int | None = None,
    line_height: int | None = None,
    encoding: str | None,
    wrap: bool = True,
) -> None:
    """Execute the text-print body. ``host._lock`` must already be held.

    ``line_height`` (ESC 3 n, in 1/180-inch units) is scoped to this
    text: it is set just before ``p.text`` and reset to the printer's
    default spacing (ESC 2) right after, so it can't leak into a following
    print on the same connection. ``None`` sends neither command.
    """
    text = validate_text_input(text)
    spacing = (
        validate_numeric_input(line_height, 0, MAX_LINE_HEIGHT, "line_height")
        if line_height is not None
        else None
    )
    align_m = map_align(align)
    ul = map_underline(underline)
    wmult = map_multiplier(width)
    hmult = map_multiplier(height)
    text_to_print = host._wrap_text(text) if wrap else text
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
                # Always sent: escpos set() skips None params and printer state is
                # sticky across connections — one inverted job would otherwise leave
                # every later print white-on-black / font B.
                invert=bool(invert),
                font=font if font in ("a", "b") else "a",
                # density=None -> escpos sends nothing; darkness is a hardware knob
                # users expect to stick until changed.
                density=density,
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
        if spacing is None:
            p.text(text_to_print)
            return
        p.line_spacing(spacing)
        try:
            p.text(text_to_print)
        except Exception:
            # Best effort: don't leave the custom spacing behind on a
            # printer that's still listening. The original error wins.
            with contextlib.suppress(Exception):
                p.line_spacing()
            raise
        p.line_spacing()

    await hass.async_add_executor_job(_do_print, printer)
