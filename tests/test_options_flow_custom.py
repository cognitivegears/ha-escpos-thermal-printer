"""Tests for the options-flow custom-profile / codepage / line-width steps."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    DOMAIN,
    OPTION_CUSTOM,
    PROFILE_CUSTOM,
)


async def _setup_entry(hass) -> MockConfigEntry:  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_PROFILE: "TM-T20",
            CONF_LINE_WIDTH: 48,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_options_flow_custom_profile_invalid(hass):  # type: ignore[no-untyped-def]
    """An invalid custom profile name should surface an error and stay on the form."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    # Submit "Custom" profile choice -> opens custom_profile step
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE: PROFILE_CUSTOM,
            CONF_CODEPAGE: "",
            CONF_LINE_WIDTH: 48,
            "default_align": "left",
            "default_cut": "none",
            "timeout": 4.0,
            "keepalive": False,
            "status_interval": 0,
        },
    )
    assert result["type"] == "form"
    assert result["step_id"] == "custom_profile"

    # Submit an invalid profile name
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"custom_profile": "definitely_not_a_real_profile_xyz123"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "custom_profile"
    assert result["errors"] == {"base": "invalid_profile"}


async def test_options_flow_custom_line_width_invalid_out_of_range(hass):  # type: ignore[no-untyped-def]
    """A line width outside 1-255 should error."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    # Submit options with custom line width
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE: "TM-T20",
            CONF_CODEPAGE: "",
            CONF_LINE_WIDTH: OPTION_CUSTOM,
            "default_align": "left",
            "default_cut": "none",
            "timeout": 4.0,
            "keepalive": False,
            "status_interval": 0,
        },
    )
    assert result["type"] == "form"
    assert result["step_id"] == "custom_line_width"

    # Submit an out-of-range width (>255)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"custom_line_width": 9999},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "custom_line_width"
    assert result["errors"] == {"base": "invalid_line_width"}


async def test_options_flow_custom_line_width_valid(hass):  # type: ignore[no-untyped-def]
    """A valid custom line width should create the entry."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE: "TM-T20",
            CONF_CODEPAGE: "",
            CONF_LINE_WIDTH: OPTION_CUSTOM,
            "default_align": "left",
            "default_cut": "none",
            "timeout": 4.0,
            "keepalive": False,
            "status_interval": 0,
        },
    )
    assert result["step_id"] == "custom_line_width"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"custom_line_width": 64},
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_LINE_WIDTH] == 64


async def test_options_flow_custom_codepage_invalid(hass):  # type: ignore[no-untyped-def]
    """An invalid custom codepage should error."""
    entry = await _setup_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE: "TM-T20",
            CONF_CODEPAGE: OPTION_CUSTOM,
            CONF_LINE_WIDTH: 48,
            "default_align": "left",
            "default_cut": "none",
            "timeout": 4.0,
            "keepalive": False,
            "status_interval": 0,
        },
    )
    assert result["type"] == "form"
    assert result["step_id"] == "custom_codepage"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"custom_codepage": "definitely_not_a_real_codepage"},
    )
    assert result["type"] == "form"
    assert result["step_id"] == "custom_codepage"
    assert result["errors"] == {"base": "invalid_codepage"}
