from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.escpos_printer.const import DOMAIN


async def test_config_flow_cannot_connect(hass):  # type: ignore[no-untyped-def]
    with patch(
        "custom_components.escpos_printer.config_flow._can_connect",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100, "timeout": 1.0},
        )
    assert result["type"] == "form"
    assert result["errors"].get("base") == "cannot_connect"
