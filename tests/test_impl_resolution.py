"""Tests for the image implementation resolution chain."""

from __future__ import annotations

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
