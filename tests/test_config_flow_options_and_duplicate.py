from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_KEEPALIVE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    DOMAIN,
)


async def test_options_flow_update(hass):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100, CONF_TIMEOUT: 4.0},
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
    # Existing configured entry
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)

    # Start new flow with same host/port
    with patch("custom_components.escpos_printer.config_flow._can_connect", return_value=True):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] == "form"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_HOST: "1.2.3.4", CONF_PORT: 9100}
        )
        assert result2["type"] == "abort"
        assert result2["reason"] == "already_configured"
