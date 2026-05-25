"""Tests for device_action/capabilities.py (registration + capability schemas)."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
import pytest
import voluptuous as vol

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.device_action.capabilities import (
    async_get_action_capabilities,
    async_get_actions,
)
from custom_components.escpos_printer.device_action.constants import (
    ACTION_BEEP,
    ACTION_CUT,
    ACTION_FEED,
    ACTION_PRINT_BARCODE,
    ACTION_PRINT_IMAGE,
    ACTION_PRINT_QR,
    ACTION_PRINT_TEXT,
    ACTION_PRINT_TEXT_UTF8,
    ACTION_TYPES,
)


async def _make_device(hass: Any, identifiers: set[tuple[str, str]]) -> str:
    """Register a device with the given identifiers and return its id."""
    from homeassistant.helpers import device_registry as dr
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={}, unique_id=str(identifiers))
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers=identifiers,
    )
    return device.id


async def test_async_get_actions_returns_eight_for_our_device(hass: Any) -> None:
    """A device with our DOMAIN identifier exposes exactly the 8 action types."""
    device_id = await _make_device(hass, {(DOMAIN, "1.2.3.4:9100")})

    actions = await async_get_actions(hass, device_id)

    assert len(actions) == len(ACTION_TYPES)
    assert {a[CONF_TYPE] for a in actions} == ACTION_TYPES
    for action in actions:
        assert action[CONF_DOMAIN] == DOMAIN
        assert action[CONF_DEVICE_ID] == device_id


async def test_async_get_actions_empty_for_foreign_device(hass: Any) -> None:
    """A device not owned by our domain returns no actions."""
    device_id = await _make_device(hass, {("some_other_domain", "abc")})

    actions = await async_get_actions(hass, device_id)

    assert actions == []


async def test_async_get_actions_empty_for_missing_device(hass: Any) -> None:
    """A device id with no registry entry returns no actions (no crash)."""
    actions = await async_get_actions(hass, "device_that_does_not_exist")
    assert actions == []


@pytest.mark.parametrize(
    ("action_type", "required_keys"),
    [
        (ACTION_PRINT_TEXT_UTF8, {"text"}),
        (ACTION_PRINT_TEXT, {"text"}),
        (ACTION_PRINT_QR, {"data"}),
        (ACTION_PRINT_IMAGE, {"image"}),
        (ACTION_PRINT_BARCODE, {"code", "bc"}),
        (ACTION_FEED, {"lines"}),
        (ACTION_CUT, {"mode"}),
        (ACTION_BEEP, set()),
    ],
)
async def test_capabilities_schema_per_action_type(
    hass: Any, action_type: str, required_keys: set[str]
) -> None:
    """Each action type returns an extra_fields schema with the right required keys."""
    caps = await async_get_action_capabilities(
        hass, {CONF_TYPE: action_type, CONF_DEVICE_ID: "x", CONF_DOMAIN: DOMAIN}
    )

    assert "extra_fields" in caps
    schema = caps["extra_fields"]
    assert isinstance(schema, vol.Schema)

    actual_required = {
        marker.schema
        for marker in schema.schema
        if isinstance(marker, vol.Required)
    }
    assert actual_required == required_keys


async def test_capabilities_unknown_action_returns_empty(hass: Any) -> None:
    """Unknown action types fall back to an empty dict rather than KeyError."""
    caps = await async_get_action_capabilities(
        hass, {CONF_TYPE: "not_a_real_action", CONF_DEVICE_ID: "x", CONF_DOMAIN: DOMAIN}
    )
    assert caps == {}


async def test_capabilities_print_barcode_rejects_unknown_bc_value(hass: Any) -> None:
    """The print_barcode bc field validates against the allowed set (regression guard)."""
    caps = await async_get_action_capabilities(
        hass, {CONF_TYPE: ACTION_PRINT_BARCODE, CONF_DEVICE_ID: "x", CONF_DOMAIN: DOMAIN}
    )
    schema = caps["extra_fields"]
    with pytest.raises(vol.Invalid):
        schema({"code": "12345", "bc": "NOT_A_BARCODE_TYPE"})
    # And a valid one passes.
    schema({"code": "12345", "bc": "CODE128"})


