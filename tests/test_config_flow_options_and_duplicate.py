"""Tests for config flow options and duplicate entry handling."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_KEEPALIVE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    CONNECTION_TYPE_NETWORK,
    DOMAIN,
)


async def test_options_flow_update(hass):  # type: ignore[no-untyped-def]
    """Test options flow allows updating settings."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)

    # Show the options form
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    # Submit options
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TIMEOUT: 5.5,
            CONF_CODEPAGE: "CP437",
            CONF_DEFAULT_ALIGN: "center",
            CONF_DEFAULT_CUT: "partial",
            CONF_KEEPALIVE: True,
            CONF_STATUS_INTERVAL: 30,
        },
    )
    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_TIMEOUT] == 5.5
    assert result2["data"][CONF_DEFAULT_ALIGN] == "center"


async def test_duplicate_unique_id_aborts(hass):  # type: ignore[no-untyped-def]
    """Test that duplicate unique ID aborts config flow."""
    # Existing configured entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)

    # Start new flow with same host/port
    with patch("custom_components.escpos_printer.config_flow.network_steps._can_connect", return_value=True):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Select network connection type
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )
        assert result2["type"] == "form"
        assert result2["step_id"] == "network"

        # Step 2: Network configuration with same host/port
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        )
        assert result3["type"] == "abort"
        assert result3["reason"] == "already_configured"
