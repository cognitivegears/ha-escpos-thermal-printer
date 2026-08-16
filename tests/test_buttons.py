"""Tests for the printer device-page buttons."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_DEFAULT_CUT, DOMAIN


@pytest.fixture(autouse=True)
def _enable_button_platform(monkeypatch):  # type: ignore[no-untyped-def]
    """conftest limits unit-test platforms to ['notify']; buttons need theirs."""
    import custom_components.escpos_printer.__init__ as cc_init

    monkeypatch.setattr(cc_init, "PLATFORMS", ["notify", "button"], raising=False)


async def _setup_entry(hass, host="1.2.3.4", options=None):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: 9100},
        options=options or {},
        title=f"ESC/POS {host}",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _button_entity_id(hass, entry, key):  # type: ignore[no-untyped-def]
    registry = er.async_get(hass)
    entity = registry.async_get_entity_id("button", DOMAIN, f"{entry.entry_id}_{key}")
    assert entity is not None, f"button {key} not registered"
    return entity


async def _press(hass, entity_id):  # type: ignore[no-untyped-def]
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)


async def test_feed_button_feeds_three_lines(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    entry.runtime_data.adapter.feed = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "feed"))
    entry.runtime_data.adapter.feed.assert_awaited_once_with(hass, lines=3)


async def test_cut_button_uses_entry_default(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass, options={CONF_DEFAULT_CUT: "partial"})
    entry.runtime_data.adapter.cut = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "cut"))
    entry.runtime_data.adapter.cut.assert_awaited_once_with(hass, mode="partial")


async def test_cut_button_none_falls_back_to_full(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass, options={CONF_DEFAULT_CUT: "none"})
    entry.runtime_data.adapter.cut = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "cut"))
    entry.runtime_data.adapter.cut.assert_awaited_once_with(hass, mode="full")


async def test_beep_button(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    entry.runtime_data.adapter.beep = AsyncMock()
    await _press(hass, _button_entity_id(hass, entry, "beep"))
    entry.runtime_data.adapter.beep.assert_awaited_once_with(hass)


async def test_sample_print_button_calls_composer(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    with patch(
        "custom_components.escpos_printer.button.async_print_sample",
        new=AsyncMock(),
    ) as sample:
        await _press(hass, _button_entity_id(hass, entry, "sample_print"))
    sample.assert_awaited_once_with(hass, entry)


async def test_buttons_attached_to_printer_device(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    registry = er.async_get(hass)
    entity_id = _button_entity_id(hass, entry, "feed")
    reg_entry = registry.async_get(entity_id)
    assert reg_entry is not None
    assert reg_entry.device_id is not None


async def test_button_press_error_is_logged_and_sanitised(hass, caplog):  # type: ignore[no-untyped-def]
    """A failed press must log via _LOGGER.exception and sanitise the message.

    Mirrors test_control_handler_sanitises_path_in_error in
    test_services_targeting.py: the pre-fix button.py swallowed the
    exception into a bare class-name message with no log output at
    all, so an offline printer produced zero diagnostics. Reusing
    ``_wrap_unexpected`` restores both the log line and the
    sanitize_log_message redaction contract shared by every other
    service handler.
    """
    entry = await _setup_entry(hass)

    async def _leak(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise OSError("usb open failed at /config/secret/db.sqlite")

    entry.runtime_data.adapter.feed = AsyncMock(side_effect=_leak)

    with caplog.at_level("ERROR"):
        with pytest.raises(HomeAssistantError) as exc_info:
            await _press(hass, _button_entity_id(hass, entry, "feed"))

    msg = str(exc_info.value)
    assert "secret/db.sqlite" not in msg, f"path leaked through sanitiser: {msg}"
    assert "[REDACTED]" in msg, f"sanitiser was bypassed: {msg}"
    assert any("feed" in rec.message and rec.levelname == "ERROR" for rec in caplog.records), (
        "no exception log emitted for the failed press"
    )
