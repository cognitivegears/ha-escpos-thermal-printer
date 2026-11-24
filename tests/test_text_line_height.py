"""Tests for the ESC/POS `line_height` field (python-escpos line_spacing()).

Named `line_height` because `line_spacing` already belongs to
print_text_image's PIL renderer (a multiplier, different semantics)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.components.notify import DOMAIN as NOTIFY_DOMAIN
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
import probatio as vol
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.services.schemas import (
    PRINT_MESSAGE_FIELDS,
    PRINT_TEXT_SCHEMA,
    PRINT_TEXT_UTF8_SCHEMA,
)


async def _setup_entry(hass: Any) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _spacing_sequence(fake: MagicMock) -> list[str]:
    """Order of line_spacing/text calls, e.g. ['line_spacing(20)', 'text', 'line_spacing()']."""
    out = []
    for name, args, _kwargs in fake.mock_calls:
        if name == "line_spacing":
            out.append(f"line_spacing({', '.join(map(str, args))})")
        elif name == "text":
            out.append("text")
    return out


@pytest.mark.parametrize("schema", [PRINT_TEXT_SCHEMA, PRINT_TEXT_UTF8_SCHEMA])
def test_line_height_schema_bounds(schema: Any) -> None:
    assert schema({"text": "x", "line_height": "24"})["line_height"] == 24
    assert schema({"text": "x", "line_height": 0})["line_height"] == 0
    assert schema({"text": "x", "line_height": 255})["line_height"] == 255
    with pytest.raises(vol.Invalid):
        schema({"text": "x", "line_height": 256})
    with pytest.raises(vol.Invalid):
        schema({"text": "x", "line_height": -1})
    assert "line_height" not in schema({"text": "x"})


def test_print_message_fields_accept_line_height() -> None:
    out = vol.Schema(PRINT_MESSAGE_FIELDS)({"message": "x", "line_height": 18})
    assert out["line_height"] == 18


@pytest.mark.parametrize("service", ["print_text", "print_text_utf8"])
async def test_line_height_is_set_then_reset_around_text(hass: Any, service: str) -> None:
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN, service, {"text": "compact", "line_height": 20}, blocking=True
        )
    assert _spacing_sequence(fake) == ["line_spacing(20)", "text", "line_spacing()"]


async def test_no_line_height_sends_no_spacing_commands(hass: Any) -> None:
    """Default behaviour is unchanged: no ESC 3 / ESC 2 bytes at all."""
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(DOMAIN, "print_text", {"text": "plain"}, blocking=True)
    fake.line_spacing.assert_not_called()


async def test_line_height_reset_attempted_when_text_fails(hass: Any) -> None:
    await _setup_entry(hass)
    fake = MagicMock()
    fake.text.side_effect = OSError("broken pipe")
    with (
        patch("escpos.printer.Network", return_value=fake),
        pytest.raises(Exception, match="broken pipe"),
    ):
        await hass.services.async_call(
            DOMAIN, "print_text", {"text": "x", "line_height": 10}, blocking=True
        )
    assert _spacing_sequence(fake) == ["line_spacing(10)", "text", "line_spacing()"]


async def test_print_message_line_height(hass: Any) -> None:
    await _setup_entry(hass)
    entity_id = next(
        e.entity_id for e in er.async_get(hass).entities.values() if e.domain == NOTIFY_DOMAIN
    )
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_message",
            {"entity_id": entity_id, "message": "hi", "line_height": 15},
            blocking=True,
        )
    assert _spacing_sequence(fake) == ["line_spacing(15)", "text", "line_spacing()"]
