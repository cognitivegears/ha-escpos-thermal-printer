from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.escpos_printer.const import DOMAIN


async def test_config_flow_success(hass):  # type: ignore[no-untyped-def]
    with patch("custom_components.escpos_printer.config_flow._can_connect", return_value=True):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        )
        assert result2["type"] == "create_entry"
        assert result2["data"][CONF_HOST] == "1.2.3.4"
