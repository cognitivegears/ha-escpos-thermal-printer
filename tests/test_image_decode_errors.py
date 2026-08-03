"""Decode-failure diagnostics: undecodable bytes must produce an actionable error.

A CDN/WAF answering a URL fetch with an HTML error/block page served as
200 used to surface as Pillow's bare ``cannot identify image file
<_io.BytesIO …>`` — useless for diagnosing what actually came back. The
``_process_bytes`` wrapper now reports the declared content type and the
size; the leading-byte sniff itself only goes to the debug log, not the
user-facing error, since echoing fetched response bytes back to the
service caller would turn the error into a content oracle.
"""

import io
import logging

from homeassistant.exceptions import HomeAssistantError
from PIL import Image
import pytest

from custom_components.escpos_printer.printer.image_operations import (
    _describe_undecodable,
    _process_bytes,
)
from custom_components.escpos_printer.printer.image_processor import ImageProcessOptions

_HTML_BODY = b"<!DOCTYPE html><html><head><title>Access denied</title></head></html>"


async def test_html_body_raises_actionable_error(hass, caplog):  # type: ignore[no-untyped-def]
    caplog.set_level(logging.DEBUG)
    with pytest.raises(HomeAssistantError) as excinfo:
        await _process_bytes(hass, _HTML_BODY, ImageProcessOptions(), content_type="text/html")
    msg = str(excinfo.value)
    assert "text/html" in msg
    assert "HTML page" in msg
    # The raw response bytes must not leak into the user-facing message --
    # they still reach the debug log for local diagnosis.
    assert "<!DOCTYPE htm" not in msg
    assert any("<!DOCTYPE htm" in rec.message for rec in caplog.records)


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
    assert "<!DOCTYPE htm" not in msg


def test_describe_undecodable_never_echoes_raw_bytes() -> None:
    """Regression: the sniffed bytes must never reach the user-facing message."""
    raw = b"\x89PNG\r\n\x1a\nnot-really-a-png-secret-marker"
    msg = _describe_undecodable(raw, "application/octet-stream")
    assert b"secret-marker" not in msg.encode()
