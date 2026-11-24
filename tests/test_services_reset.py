"""Tests for the `reset` service / device action (ESC @, python-escpos hw("INIT"))."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_PORT, CONF_TYPE
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
import probatio as vol
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.device_action import (
    ACTION_SCHEMA,
    async_call_action_from_config,
    async_get_actions,
)
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig
from custom_components.escpos_printer.printer.network_adapter import NetworkPrinterAdapter
from custom_components.escpos_printer.services.schemas import RESET_SCHEMA


class _FakeHass:
    async def async_add_executor_job(self, fn, *args):  # type: ignore[no-untyped-def]
        return fn(*args)


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


async def test_reset_service_sends_hw_init(hass: Any) -> None:
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(DOMAIN, "reset", {}, blocking=True)
    fake.hw.assert_called_once_with("INIT")
    # A reset is a control op: no text, no paper movement.
    fake.text.assert_not_called()
    fake.cut.assert_not_called()


async def test_reset_service_adapter_error_raises_homeassistant_error(hass: Any) -> None:
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("printer gone")

    with (
        patch.object(adapter, "reset", side_effect=_boom),
        pytest.raises(HomeAssistantError, match="printer gone"),
    ):
        await hass.services.async_call(DOMAIN, "reset", {}, blocking=True)


def test_reset_schema_accepts_target_only() -> None:
    assert RESET_SCHEMA({"device_id": "abc"})["device_id"] == "abc"
    assert RESET_SCHEMA({})["broadcast"] is False
    with pytest.raises(vol.Invalid):
        RESET_SCHEMA({"lines": 3})
    with pytest.raises(vol.Invalid):
        RESET_SCHEMA({"broadcast": True, "device_id": "abc"})


async def test_adapter_reset_marks_success_but_not_last_print() -> None:
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]

    await adapter.reset(_FakeHass())  # type: ignore[arg-type]

    printer.hw.assert_called_once_with("INIT")
    printer.close.assert_called_once()
    assert adapter._last_ok is not None
    assert adapter._last_print is None


async def test_adapter_reset_failure_marks_offline() -> None:
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.hw.side_effect = OSError("broken pipe")
    adapter._connect = lambda: printer  # type: ignore[method-assign]

    with pytest.raises(OSError):
        await adapter.reset(_FakeHass())  # type: ignore[arg-type]
    assert adapter.get_status() is False
    assert adapter._last_error_reason == "print operation failed"


async def _device_id(hass: Any, entry: MockConfigEntry) -> str:
    device = next(iter(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)), None)
    assert device is not None
    return device.id


async def test_reset_device_action_listed_and_calls_adapter(hass: Any) -> None:
    entry = await _setup_entry(hass)
    device_id = await _device_id(hass, entry)

    actions = await async_get_actions(hass, device_id)
    assert any(a[CONF_TYPE] == "reset" for a in actions)

    config = ACTION_SCHEMA({"domain": DOMAIN, CONF_DEVICE_ID: device_id, CONF_TYPE: "reset"})
    adapter = entry.runtime_data.adapter
    with patch.object(adapter, "reset", wraps=adapter.reset) as spy:
        await async_call_action_from_config(hass, config, {}, None)
    spy.assert_called_once_with(hass)
