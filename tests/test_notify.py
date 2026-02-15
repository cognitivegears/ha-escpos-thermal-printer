from unittest.mock import MagicMock, patch

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
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
    return entry


def _get_notify_entity_id(hass):  # type: ignore[no-untyped-def]
    registry = er.async_get(hass)
    entities = [e for e in registry.entities.values() if e.domain == NOTIFY_DOMAIN]
    assert entities, "No notify entities registered"
    return entities[0].entity_id


async def test_notify_sends_text(hass):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    entity_id = _get_notify_entity_id(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "message": "Hello"},
            blocking=True,
        )
    assert fake.text.called or fake.cut.called or fake.control.called


async def test_notify_send_message_uses_normal_text_size(hass):  # type: ignore[no-untyped-def]
    """Test that standard send_message explicitly resets text size to normal."""
    await _setup_entry(hass)
    entity_id = _get_notify_entity_id(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            NOTIFY_DOMAIN,
            "send_message",
            {"entity_id": entity_id, "message": "Normal"},
            blocking=True,
        )
    fake.set.assert_called_once()
    kw = fake.set.call_args.kwargs
    assert kw["custom_size"] is False
    assert kw["normal_textsize"] is True


async def test_print_message_entity_service_with_formatting(hass):  # type: ignore[no-untyped-def]
    """Test the custom print_message entity service passes text formatting."""
    await _setup_entry(hass)
    entity_id = _get_notify_entity_id(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {
                "entity_id": entity_id,
                "message": "ALERT",
                "bold": True,
                "width": "double",
                "height": "double",
                "underline": "single",
                "align": "center",
            },
            blocking=True,
        )
    fake.set.assert_called_once()
    kw = fake.set.call_args.kwargs
    assert kw["bold"] is True
    assert kw["width"] == 2
    assert kw["height"] == 2
    assert kw["custom_size"] is True
    assert kw["underline"] == 1
    assert kw["align"] == "center"


async def test_print_message_entity_service_defaults(hass):  # type: ignore[no-untyped-def]
    """Test that print_message uses sensible defaults when no formatting specified."""
    await _setup_entry(hass)
    entity_id = _get_notify_entity_id(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {"entity_id": entity_id, "message": "Simple text"},
            blocking=True,
        )
    fake.set.assert_called_once()
    kw = fake.set.call_args.kwargs
    assert kw["bold"] is False
    assert kw["custom_size"] is False
    assert kw["normal_textsize"] is True


async def test_print_message_with_title(hass):  # type: ignore[no-untyped-def]
    """Test that print_message prepends title to message."""
    await _setup_entry(hass)
    entity_id = _get_notify_entity_id(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {"entity_id": entity_id, "message": "Body text", "title": "Header"},
            blocking=True,
        )
    # The printed text should contain both title and message
    printed_text = fake.text.call_args[0][0]
    assert "Header" in printed_text
    assert "Body text" in printed_text


async def test_print_message_utf8_mode(hass):  # type: ignore[no-untyped-def]
    """Test that print_message with utf8=True transcodes text."""
    await _setup_entry(hass)
    entity_id = _get_notify_entity_id(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake), patch(
        "custom_components.escpos_printer.notify.transcode_to_codepage",
        return_value="transcoded text",
    ) as mock_transcode:
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {"entity_id": entity_id, "message": "Caf\u00e9 cr\u00e8me", "utf8": True},
            blocking=True,
        )
    # transcode_to_codepage should have been called
    mock_transcode.assert_called_once()
    # The transcoded text should be what gets printed
    printed_text = fake.text.call_args[0][0]
    assert printed_text == "transcoded text"
