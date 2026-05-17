"""Tests for the Bluetooth battery sensor entity."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.escpos_printer.const import (
    CONF_BT_MAC,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
)
from custom_components.escpos_printer.sensor import (
    BluetoothPrinterBatterySensor,
    LastImagePrintSensor,
    async_setup_entry,
)


class _FakeEntry:
    """Lightweight stand-in for ConfigEntry — only the attrs the sensor reads."""

    def __init__(
        self,
        entry_id: str = "abc",
        title: str = "Netum",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}


async def test_sensor_async_setup_entry_skips_battery_for_non_bluetooth():
    """Non-Bluetooth entries should only register the last-print sensor."""
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    add = MagicMock()
    await async_setup_entry(MagicMock(), entry, add)  # type: ignore[arg-type]
    add.assert_called_once()
    sensors = list(add.call_args.args[0])
    assert not any(
        isinstance(s, BluetoothPrinterBatterySensor) for s in sensors
    )
    assert any(isinstance(s, LastImagePrintSensor) for s in sensors)


async def test_sensor_async_setup_entry_skips_battery_for_bluetooth_without_mac():
    """A Bluetooth entry missing the MAC should still register the last-print sensor."""
    entry = _FakeEntry(
        data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH, CONF_BT_MAC: ""}
    )
    add = MagicMock()
    await async_setup_entry(MagicMock(), entry, add)  # type: ignore[arg-type]
    add.assert_called_once()
    sensors = list(add.call_args.args[0])
    assert not any(
        isinstance(s, BluetoothPrinterBatterySensor) for s in sensors
    )


async def test_sensor_async_setup_entry_creates_for_bluetooth_with_mac():
    """A Bluetooth entry with a MAC should create both sensors."""
    entry = _FakeEntry(
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
        }
    )
    add = MagicMock()
    await async_setup_entry(MagicMock(), entry, add)  # type: ignore[arg-type]
    add.assert_called_once()
    sensors = list(add.call_args.args[0])
    assert any(
        isinstance(s, BluetoothPrinterBatterySensor) for s in sensors
    )
    assert any(isinstance(s, LastImagePrintSensor) for s in sensors)


def test_battery_sensor_device_info_includes_title():
    sensor = BluetoothPrinterBatterySensor(_FakeEntry(title="Phomemo M02"), "AA:BB:CC:DD:EE:FF")
    info = sensor.device_info
    assert "Phomemo M02" in info["name"]


@pytest.mark.asyncio
async def test_sensor_uses_bluez_percentage_when_available():
    sensor = BluetoothPrinterBatterySensor(_FakeEntry(), "AA:BB:CC:DD:EE:FF")
    with patch(
        "custom_components.escpos_printer.sensor.query_bt_battery_percentage",
        new=AsyncMock(return_value=72),
    ):
        await sensor.async_update()
    assert sensor.available is True
    assert sensor.native_value == 72


@pytest.mark.asyncio
async def test_sensor_unavailable_when_bluez_returns_none():
    sensor = BluetoothPrinterBatterySensor(_FakeEntry(), "AA:BB:CC:DD:EE:FF")
    with patch(
        "custom_components.escpos_printer.sensor.query_bt_battery_percentage",
        new=AsyncMock(return_value=None),
    ):
        await sensor.async_update()
    assert sensor.available is False
    assert sensor.native_value is None


@pytest.mark.asyncio
async def test_sensor_unavailable_on_query_exception():
    """A bluez-side error must mark unavailable, not crash HA."""
    sensor = BluetoothPrinterBatterySensor(_FakeEntry(), "AA:BB:CC:DD:EE:FF")
    with patch(
        "custom_components.escpos_printer.sensor.query_bt_battery_percentage",
        new=AsyncMock(side_effect=RuntimeError("bluez exploded")),
    ):
        await sensor.async_update()
    assert sensor.available is False


@pytest.mark.asyncio
async def test_sensor_unique_id_is_per_entry():
    sensor_a = BluetoothPrinterBatterySensor(_FakeEntry("a"), "AA:BB:CC:DD:EE:FF")
    sensor_b = BluetoothPrinterBatterySensor(_FakeEntry("b"), "11:22:33:44:55:66")
    assert sensor_a.unique_id == "a_battery"
    assert sensor_b.unique_id == "b_battery"
    assert sensor_a.unique_id != sensor_b.unique_id


@pytest.mark.asyncio
async def test_sensor_marked_diagnostic():
    """Battery sensors should live under the device's diagnostics section."""
    from homeassistant.helpers.entity import EntityCategory

    sensor = BluetoothPrinterBatterySensor(_FakeEntry(), "AA:BB:CC:DD:EE:FF")
    assert sensor.entity_category is EntityCategory.DIAGNOSTIC
