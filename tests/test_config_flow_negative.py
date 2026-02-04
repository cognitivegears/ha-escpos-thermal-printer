from unittest.mock import patch

from homeassistant import config_entries

from custom_components.escpos_printer.const import CONF_PRINTER_NAME, DOMAIN


async def test_config_flow_cannot_connect(hass):  # type: ignore[no-untyped-def]
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=False,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": config_entries.SOURCE_USER},
            data={CONF_PRINTER_NAME: "TestPrinter", "timeout": 1.0},
        )
    assert result["type"] == "form"
    assert result["errors"].get("base") == "cannot_connect"
