"""Tests for the Bluetooth battery sensor entity."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.escpos_printer.sensor import BluetoothPrinterBatterySensor


class _FakeEntry:
    """Lightweight stand-in for ConfigEntry — only the attrs the sensor reads."""

    def __init__(self, entry_id: str = "abc", title: str = "Netum") -> None:
        self.entry_id = entry_id
        self.title = title


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
