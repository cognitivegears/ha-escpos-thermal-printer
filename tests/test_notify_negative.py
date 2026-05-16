from unittest.mock import MagicMock, patch

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_notify(hass):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={"host": "1.2.3.4", "port": 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.domain == NOTIFY_DOMAIN]
    assert entities
    return entities[0].entity_id


async def test_notify_error_bubbles_as_exception(hass, caplog):  # type: ignore[no-untyped-def]
    entity_id = await _setup_notify(hass)

    fake = MagicMock()
    fake.text.side_effect = RuntimeError("bad printer")
    with patch("escpos.printer.Network", return_value=fake), pytest.raises(Exception) as excinfo:
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "message": "Hello"},
            blocking=True,
        )
    # The notify error is now sanitized and surfaced via the raised
    # HomeAssistantError (not a separate _LOGGER.error call — that was
    # the "double-log anti-pattern" Phase 2 BP-M2 flagged). The message
    # text still contains "print_message failed".
    assert "print_message failed" in str(excinfo.value)


async def test_notify_handles_title_and_message(hass):  # type: ignore[no-untyped-def]
    entity_id = await _setup_notify(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "title": "T", "message": "M"},
            blocking=True,
        )
    # Text should be sent with title and message combined
    assert fake.text.called
