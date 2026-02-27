import sys
from unittest.mock import patch

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_PRINTER_NAME, DOMAIN


async def _setup_notify(hass):  # type: ignore[no-untyped-def]
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
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.domain == NOTIFY_DOMAIN]
    assert entities
    return entities[0].entity_id


async def test_notify_error_bubbles_as_exception(hass, caplog):  # type: ignore[no-untyped-def]
    entity_id = await _setup_notify(hass)

    dummy_cls = sys.modules["escpos.printer"].Dummy
    with patch.object(dummy_cls, "text", side_effect=RuntimeError("bad printer")), pytest.raises(Exception):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "message": "Hello"},
            blocking=True,
        )
    assert any("print_message failed" in rec.message for rec in caplog.records)


async def test_notify_handles_title_and_message(hass):  # type: ignore[no-untyped-def]
    entity_id = await _setup_notify(hass)

    dummy_cls = sys.modules["escpos.printer"].Dummy
    with patch.object(dummy_cls, "text") as mock_text:
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "title": "T", "message": "M"},
            blocking=True,
        )
    # Text should be sent with title and message combined
    assert mock_text.called
