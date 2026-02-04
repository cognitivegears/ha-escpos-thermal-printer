from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_PRINTER_NAME, DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TestPrinter",
        data={CONF_PRINTER_NAME: "TestPrinter"},
        unique_id="cups_TestPrinter",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Dummy"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_print_text_service(hass):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Dummy", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello"},
            blocking=True,
        )
    assert fake.text.called
