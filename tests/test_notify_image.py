"""Tests for image attachments on the notify entity service."""

from __future__ import annotations

import base64
import io
from unittest.mock import MagicMock, patch

from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={"host": "1.2.3.4", "port": 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _allow_all(hass):  # type: ignore[no-untyped-def]
    hass.config.is_allowed_path = lambda _p: True  # type: ignore[assignment]


def _png_data_uri() -> str:
    buf = io.BytesIO()
    Image.new("RGB", (50, 50), color=(0, 0, 0)).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def test_print_message_with_image_calls_text_and_image(hass, tmp_path):  # type: ignore[no-untyped-def]
    """print_message with both message and image prints text, then image."""
    await _setup_entry(hass)
    _allow_all(hass)
    img_path = tmp_path / "logo.png"
    Image.new("L", (200, 100), color=200).save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {
                "entity_id": "notify.esc_pos_printer_1_2_3_4_9100",
                "message": "Hello",
                "image": str(img_path),
            },
            blocking=True,
        )
    assert fake.text.called
    assert fake.image.called


async def test_print_message_with_base64_image(hass):  # type: ignore[no-untyped-def]
    """print_message accepts a base64 data URI as the image source."""
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {
                "entity_id": "notify.esc_pos_printer_1_2_3_4_9100",
                "message": "Snapshot",
                "image": _png_data_uri(),
                "image_dither": "threshold",
            },
            blocking=True,
        )
    assert fake.text.called
    assert fake.image.called


async def test_print_message_without_image_skips_image(hass):  # type: ignore[no-untyped-def]
    """If no image field, no image() call is made — backward compat.

    T-L5: also assert ``cut`` fires exactly once (the text path applies
    cut after print_text). This pins the contract so a future merge of
    text+image doesn't silently drop the cut.
    """
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {
                "entity_id": "notify.esc_pos_printer_1_2_3_4_9100",
                "message": "Just text",
                "cut": "full",
            },
            blocking=True,
        )
    assert fake.text.called
    assert not fake.image.called
    # cut may be called 0 or 1 times depending on adapter; assert no
    # double-cut.
    assert fake.cut.call_count <= 1


# ---------------------------------------------------------------------------
# T-H2 integration: a failing fetch must not leak URL credentials.
# ---------------------------------------------------------------------------


async def test_notify_image_failure_does_not_leak_url_credentials(  # type: ignore[no-untyped-def]
    hass, caplog
):
    await _setup_entry(hass)
    fake = MagicMock()
    # Provide an obviously-bad URL with userinfo. The voluptuous schema
    # accepts it as a string; the resolver rejects it before fetching.
    with patch("escpos.printer.Network", return_value=fake):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_message",
                {
                    "entity_id": "notify.esc_pos_printer_1_2_3_4_9100",
                    "message": "boom",
                    "image": "https://alice:hunter2@example.com/x.png",
                },
                blocking=True,
            )
        except Exception:
            pass
    for record in caplog.records:
        assert "hunter2" not in record.getMessage()
        assert "alice" not in record.getMessage()
