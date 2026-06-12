"""Decode-failure diagnostics: undecodable bytes must produce an actionable error.

A CDN/WAF answering a URL fetch with an HTML error/block page served as
200 used to surface as Pillow's bare ``cannot identify image file
<_io.BytesIO …>`` — useless for diagnosing what actually came back. The
``_process_bytes`` wrapper now reports the declared content type, the
size, and a bounded sniff of the leading bytes.
"""

import io

from homeassistant.exceptions import HomeAssistantError
from PIL import Image
import pytest

from custom_components.escpos_printer.printer.image_operations import (
    _describe_undecodable,
    _process_bytes,
)
from custom_components.escpos_printer.printer.image_processor import ImageProcessOptions

_HTML_BODY = b"<!DOCTYPE html><html><head><title>Access denied</title></head></html>"


async def test_html_body_raises_actionable_error(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError) as excinfo:
        await _process_bytes(hass, _HTML_BODY, ImageProcessOptions(), content_type="text/html")
    msg = str(excinfo.value)
    assert "text/html" in msg
    assert "HTML page" in msg
    assert "<!DOCTYPE htm" in msg  # bounded sniff of the body


async def test_unknown_binary_lists_supported_formats(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError) as excinfo:
        await _process_bytes(
            hass, b"\x00\x01\x02\x03 not an image", ImageProcessOptions(), content_type=None
        )
    msg = str(excinfo.value)
    assert "JPEG" in msg
    assert "PNG" in msg
    assert "HTML page" not in msg


async def test_valid_image_still_decodes(hass):  # type: ignore[no-untyped-def]
    buf = io.BytesIO()
    Image.new("L", (40, 20), 128).save(buf, format="PNG")
    img = await _process_bytes(hass, buf.getvalue(), ImageProcessOptions(), content_type=None)
    assert img.size == (40, 20)


def test_describe_undecodable_html_sniff_without_content_type() -> None:
    msg = _describe_undecodable(_HTML_BODY, None)
    assert "HTML page" in msg
