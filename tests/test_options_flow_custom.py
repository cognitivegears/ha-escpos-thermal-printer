"""Tests for the options-flow custom-profile / codepage / line-width steps."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.escpos_printer.const import (
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_RELIABILITY_PROFILE,
    CONF_RFCOMM_CHANNEL,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    CONNECTION_TYPE_BLUETOOTH,
    DOMAIN,
    OPTION_CUSTOM,
    PROFILE_CUSTOM,
    RELIABILITY_PROFILE_AUTO,
)


async def _open_settings(hass, entry: MockConfigEntry):  # type: ignore[no-untyped-def]
    """Open the options flow and hop through the menu to the settings form."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
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

    result = await _open_settings(hass, entry)
    assert result["type"] == "form"

    # Submit "Custom" profile choice -> opens custom_profile step
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE: PROFILE_CUSTOM,
            CONF_CODEPAGE: "",
            CONF_LINE_WIDTH: "48",
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

    result = await _open_settings(hass, entry)
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

    result = await _open_settings(hass, entry)
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

    # Saving schedules an automatic entry reload (OptionsFlowWithReload);
    # patch the setup so the reload can't leave a half-finished real setup
    # (and its delayed Store writes) lingering past the end of the test.
    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input={"custom_line_width": 64},
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_LINE_WIDTH] == 64


async def test_options_flow_bluetooth_reliability_defaults_to_auto(hass):  # type: ignore[no-untyped-def]
    """B7: the options form for a Bluetooth entry with no stored reliability
    profile must default to "auto" -- the same fallback __init__.py uses at
    runtime -- not "bluetooth_safe". Otherwise opening options and pressing
    Submit with no changes silently switches the entry's print throttling.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )
    entry.add_to_hass(hass)

    result = await _open_settings(hass, entry)
    assert result["type"] == "form"

    defaults = {
        key.schema: key.default()
        for key in result["data_schema"].schema
        if isinstance(key, vol.Optional) and not isinstance(key.default, vol.Undefined)
    }
    assert defaults[CONF_RELIABILITY_PROFILE] == RELIABILITY_PROFILE_AUTO


async def test_options_flow_bluetooth_status_interval_still_defaults_to_0(hass):  # type: ignore[no-untyped-def]
    """The options form for a Bluetooth entry with no stored status_interval
    must default to 0 -- the same runtime default __init__.py applies.
    Bluetooth status checks open a real RFCOMM connection and many cheap
    printers beep on every connect, so polling stays opt-in.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )
    entry.add_to_hass(hass)

    result = await _open_settings(hass, entry)
    assert result["type"] == "form"

    defaults = {
        key.schema: key.default()
        for key in result["data_schema"].schema
        if isinstance(key, vol.Optional) and not isinstance(key.default, vol.Undefined)
    }
    assert defaults[CONF_STATUS_INTERVAL] == 0


async def test_options_flow_network_status_interval_still_defaults_to_0(hass):  # type: ignore[no-untyped-def]
    """A network entry's status_interval default is unaffected (stays 0)."""
    entry = await _setup_entry(hass)

    result = await _open_settings(hass, entry)
    assert result["type"] == "form"

    defaults = {
        key.schema: key.default()
        for key in result["data_schema"].schema
        if isinstance(key, vol.Optional) and not isinstance(key.default, vol.Undefined)
    }
    assert defaults[CONF_STATUS_INTERVAL] == 0


async def test_options_flow_custom_codepage_invalid(hass):  # type: ignore[no-untyped-def]
    """An invalid custom codepage should error."""
    entry = await _setup_entry(hass)

    result = await _open_settings(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_PROFILE: "TM-T20",
            CONF_CODEPAGE: OPTION_CUSTOM,
            CONF_LINE_WIDTH: "48",
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


def _bt_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )


def _options_submission(**overrides):  # type: ignore[no-untyped-def]
    data = {
        CONF_PROFILE: "",
        CONF_CODEPAGE: "",
        CONF_LINE_WIDTH: "42",
        "default_align": "left",
        "default_cut": "none",
        "reliability_profile": RELIABILITY_PROFILE_AUTO,
        "timeout": 4.0,
        "status_interval": 0,
        "allow_local_image_urls": False,
    }
    data.update(overrides)
    return data


async def test_options_flow_bt_status_interval_below_floor_errors(hass):  # type: ignore[no-untyped-def]
    """1-59 seconds must be rejected for a Bluetooth entry (recommended floor is 60s)."""
    entry = _bt_entry()
    entry.add_to_hass(hass)

    result = await _open_settings(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=_options_submission(status_interval=30),
    )
    assert result["type"] == "form"
    assert result["step_id"] == "settings"
    assert result["errors"] == {"base": "bt_status_interval_too_low"}
    # Entry untouched -- the invalid submission was never saved.
    assert entry.options.get("status_interval") is None


async def test_options_flow_bt_status_interval_zero_accepted(hass):  # type: ignore[no-untyped-def]
    """0 (polling disabled) is a valid value for a Bluetooth entry."""
    entry = _bt_entry()
    entry.add_to_hass(hass)

    result = await _open_settings(hass, entry)
    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=_options_submission(status_interval=0),
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_STATUS_INTERVAL] == 0


async def test_options_flow_bt_status_interval_floor_accepted(hass):  # type: ignore[no-untyped-def]
    """60 seconds (the floor itself) is accepted for a Bluetooth entry."""
    entry = _bt_entry()
    entry.add_to_hass(hass)

    result = await _open_settings(hass, entry)
    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=_options_submission(status_interval=60),
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_STATUS_INTERVAL] == 60


async def test_options_flow_non_bt_entry_status_interval_below_60_accepted(hass):  # type: ignore[no-untyped-def]
    """The floor only applies to Bluetooth entries -- a network entry accepts 30s."""
    entry = await _setup_entry(hass)

    result = await _open_settings(hass, entry)
    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=_options_submission(profile="TM-T20", line_width="48", status_interval=30),
        )
        await hass.async_block_till_done()
    assert result["type"] == "create_entry"
    assert result["data"][CONF_STATUS_INTERVAL] == 30
