"""Tests for the image implementation resolution chain."""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

from PIL import Image

from custom_components.escpos_printer.const import (
    CONF_IMPL,
    IMPL_AUTO,
    IMPL_CHOICE_LABELS,
    IMPL_MODES,
)
from custom_components.escpos_printer.printer import create_printer_adapter
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig


def test_impl_labels_cover_all_modes() -> None:
    assert set(IMPL_CHOICE_LABELS) == {IMPL_AUTO, *IMPL_MODES}


def test_conf_impl_key() -> None:
    assert CONF_IMPL == "impl"


def test_adapter_default_impl_attrs() -> None:
    adapter = create_printer_adapter(NetworkPrinterConfig(host="127.0.0.1"))
    assert adapter.default_impl is None
    assert adapter.profile_no_image_support is False


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color=(0, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


def _make_host() -> MagicMock:
    host = MagicMock()
    host.allow_local_image_urls = False
    host.get_profile_pixel_width.return_value = 384
    host.reliability_profile_defaults = {}
    host.default_chunk_delay_ms = 0
    host._image_stats = None
    host.default_impl = "bitImageColumn"
    host.profile_no_image_support = False
    return host


async def test_prepare_image_uses_adapter_default_impl(hass) -> None:  # type: ignore[no-untyped-def]
    """Adapter default_impl wins when no per-call impl is given, and a
    per-call impl overrides it.
    """
    from custom_components.escpos_printer.printer import image_operations

    async def _capture(_hass, _img, **_kwargs):  # type: ignore[no-untyped-def]
        return _png_bytes(), "image/png"

    host = _make_host()
    with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
        prepared = await image_operations.prepare_image_for_print(
            host, hass, "http://192.168.1.5/x.png"
        )
    assert prepared.impl == "bitImageColumn"

    with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
        prepared = await image_operations.prepare_image_for_print(
            host, hass, "http://192.168.1.5/x.png", impl="graphics"
        )
    assert prepared.impl == "graphics"


async def test_prepare_image_uses_legacy_preset_impl_rung(hass) -> None:  # type: ignore[no-untyped-def]
    """reliability_profile_defaults["impl"] outranks adapter.default_impl
    when no per-call impl is given (legacy preset rung in the resolution
    chain -- presets no longer carry an impl, but honor one if present).
    """
    from custom_components.escpos_printer.printer import image_operations

    async def _capture(_hass, _img, **_kwargs):  # type: ignore[no-untyped-def]
        return _png_bytes(), "image/png"

    host = _make_host()
    host.reliability_profile_defaults = {"impl": "graphics"}
    host.default_impl = None
    with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
        prepared = await image_operations.prepare_image_for_print(
            host, hass, "http://192.168.1.5/x.png"
        )
    assert prepared.impl == "graphics"


async def test_prepare_image_warns_once_for_no_image_support_profile(  # type: ignore[no-untyped-def]
    hass, caplog
) -> None:
    """profile_no_image_support=True warns exactly once, then stops warning."""
    from custom_components.escpos_printer.printer import image_operations

    async def _capture(_hass, _img, **_kwargs):  # type: ignore[no-untyped-def]
        return _png_bytes(), "image/png"

    host = _make_host()
    host.profile_no_image_support = True
    host._no_image_warned = False
    with caplog.at_level("WARNING"):
        with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
            await image_operations.prepare_image_for_print(host, hass, "http://192.168.1.5/x.png")
            await image_operations.prepare_image_for_print(host, hass, "http://192.168.1.5/x.png")

    warnings = [r for r in caplog.records if "no image support" in r.message.lower()]
    assert len(warnings) == 1
    assert host._no_image_warned is True


async def test_prepare_image_never_warns_when_host_lacks_no_image_attrs(  # type: ignore[no-untyped-def]
    hass, caplog
) -> None:
    """A host missing profile_no_image_support/_no_image_warned entirely
    (getattr defaults: False / True) must never warn."""
    from custom_components.escpos_printer.printer import image_operations

    async def _capture(_hass, _img, **_kwargs):  # type: ignore[no-untyped-def]
        return _png_bytes(), "image/png"

    host = _make_host()
    # Deliberately no profile_no_image_support / _no_image_warned -- both
    # getattr() calls in the warn-once check fall back to their defaults
    # (False / True), so a plain host missing these attrs must never warn.
    del host.profile_no_image_support
    del host._no_image_warned

    with caplog.at_level("WARNING"):
        with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
            await image_operations.prepare_image_for_print(host, hass, "http://192.168.1.5/x.png")

    assert not any("no image support" in r.message.lower() for r in caplog.records)


async def test_prepare_image_explicit_width_beats_narrower_profile(hass) -> None:  # type: ignore[no-untyped-def]
    """Real pipeline (no mocked process step): width=576 beats a 384px
    profile -- the pipeline only ever downscales, so an explicit width
    wider than the profile must not get clamped.

    This is why the calibration wizard's width-bar step passes
    ``width=w`` per bar instead of relying on the profile width.
    """
    from custom_components.escpos_printer._config_flow.calibration import width_bar_data_uri
    from custom_components.escpos_printer.printer import image_operations

    async def _capture(_hass, _img, **_kwargs):  # type: ignore[no-untyped-def]
        raw = base64.b64decode(width_bar_data_uri(576).split(",", 1)[1])
        return raw, "image/png"

    host = _make_host()
    host.get_profile_pixel_width.return_value = 384
    with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
        prepared = await image_operations.prepare_image_for_print(
            host,
            hass,
            "data:image/png;base64,x",
            width=576,
            auto_resize=False,
            dither="threshold",
        )
    assert prepared.img_obj.width == 576

    # Negative: width=None clamps to the narrower profile width.
    with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
        prepared = await image_operations.prepare_image_for_print(
            host,
            hass,
            "data:image/png;base64,x",
            width=None,
            auto_resize=False,
            dither="threshold",
        )
    assert prepared.img_obj.width == 384
