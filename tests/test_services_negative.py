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


async def test_print_image_service_bad_path(hass):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake), pytest.raises(Exception) as excinfo:
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": "/non/existent.png"},
            blocking=True,
        )
    # `Path.resolve(strict=True)` raises FileNotFoundError → wrapped as
    # "Image file does not exist or is not a regular file".
    assert "does not exist" in str(excinfo.value) or "print_image failed" in str(excinfo.value)


async def test_cut_invalid_mode_rejected_by_schema(hass):  # type: ignore[no-untyped-def]
    """`mode: invalid` is now rejected by the cut-service schema (BP-C1).

    Previously the handler accepted anything and warned at runtime; the
    schema is the right enforcement point.
    """
    import voluptuous as vol

    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake), pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "cut",
            {"mode": "invalid"},
            blocking=True,
        )
    fake.cut.assert_not_called()


async def test_feed_zero_rejected_by_schema(hass):  # type: ignore[no-untyped-def]
    """`lines: 0` is now rejected by the feed-service schema (min=1).

    Previously the handler clamped silently; the schema is the right
    enforcement point.
    """
    import voluptuous as vol

    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake), pytest.raises(vol.Invalid):
        await hass.services.async_call(
            DOMAIN,
            "feed",
            {"lines": 0},
            blocking=True,
        )
    fake.control.assert_not_called()
