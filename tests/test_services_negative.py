from unittest.mock import MagicMock, patch

import pytest
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


async def test_print_text_service_raises_homeassistanterror(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)

    fake = MagicMock()
    fake.text.side_effect = RuntimeError("boom")
    with patch("escpos.printer.Network", return_value=fake), pytest.raises(Exception):
        # HomeAssistantError bubbles up from service call
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello"},
            blocking=True,
        )
    # We expect an error log mentioning print_text failed
    assert any("print_text failed" in rec.message for rec in caplog.records)


async def test_print_image_service_bad_path(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake), pytest.raises(Exception):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": "/non/existent.png"},
            blocking=True,
        )
    assert any("Opening local image" in rec.message for rec in caplog.records)


async def test_cut_invalid_mode_logs_warning(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "cut",
            {"mode": "invalid"},
            blocking=True,
        )
    # Should warn and default to full
    assert any("Invalid cut mode" in rec.message for rec in caplog.records)
    fake.cut.assert_called()  # still called


async def test_feed_clamps_and_executes(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "feed",
            {"lines": 0},
            blocking=True,
        )
    # Should clamp to at least 1
    assert any("Feeding" in rec.message for rec in caplog.records)
    assert fake.control.called
