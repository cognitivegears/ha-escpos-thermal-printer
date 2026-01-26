from unittest.mock import MagicMock, patch

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_PRINTER_NAME, DOMAIN


async def test_notify_sends_text(hass):  # type: ignore[no-untyped-def]
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

    # Find the created notify entity
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.domain == NOTIFY_DOMAIN]
    assert entities, "No notify entities registered"
    entity_id = entities[0].entity_id

    fake = MagicMock()
    with patch("escpos.printer.Dummy", return_value=fake):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "message": "Hello"},
            blocking=True,
        )
    assert fake.text.called or fake.cut.called or fake.control.called
