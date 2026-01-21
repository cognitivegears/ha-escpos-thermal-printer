from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_NETWORK,
    DOMAIN,
)


async def test_config_flow_cannot_connect(hass):  # type: ignore[no-untyped-def]
    """Test config flow with connection failure shows error."""
    with patch(
        "custom_components.escpos_printer.config_flow._can_connect",
        return_value=False,
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Select network connection type
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )
        assert result2["type"] == "form"
        assert result2["step_id"] == "network"

        # Step 2: Network configuration (will fail)
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100, "timeout": 1.0},
        )

        # Should show form again with error
        assert result3["type"] == "form"
        assert result3["step_id"] == "network"
        assert result3["errors"].get("base") == "cannot_connect"
