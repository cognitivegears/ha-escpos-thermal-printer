"""Tests for the printer-not-calibrated repairs issue and fix flow."""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_LINE_WIDTH, DOMAIN


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


def _issue(hass, entry):  # type: ignore[no-untyped-def]
    registry = ir.async_get(hass)
    return registry.async_get_issue(DOMAIN, f"printer_not_calibrated_{entry.entry_id}")


async def test_uncalibrated_entry_raises_issue(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    issue = _issue(hass, entry)
    assert issue is not None
    assert issue.is_fixable
    assert issue.translation_key == "printer_not_calibrated"


async def test_calibrated_entry_has_no_issue(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass, options={CONF_LINE_WIDTH: 42})
    assert _issue(hass, entry) is None


async def test_issue_cleared_after_calibration_reload(hass):  # type: ignore[no-untyped-def]
    """Saving a calibration option and reloading (what the wizard does) clears the issue."""
    entry = await _setup_entry(hass)
    assert _issue(hass, entry) is not None
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_LINE_WIDTH: 42})
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
    assert _issue(hass, entry) is None


async def test_fix_flow_opens_wizard_confirm_step(hass):  # type: ignore[no-untyped-def]
    entry = await _setup_entry(hass)
    from custom_components.escpos_printer.repairs import async_create_fix_flow

    flow = await async_create_fix_flow(
        hass,
        f"printer_not_calibrated_{entry.entry_id}",
        {"entry_id": entry.entry_id},
    )
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_confirm"
