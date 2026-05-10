"""Sensor platform — exposes BT-printer battery level when bluez tracks it.

Most cheap thermal printers don't expose ``org.bluez.Battery1``, so for
those the entity stays unavailable. Portable / battery-powered models
(Phomemo M02, newer Netum firmware, some Cashino models) do, and this
gives users a real "low battery" signal they can automate on.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .bluez import query_bt_battery_percentage
from .const import (
    CONF_BT_MAC,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Add a battery sensor for Bluetooth printers.

    Network and USB printers don't have battery state to report — we only
    create the sensor for the BT branch.
    """
    if entry.data.get(CONF_CONNECTION_TYPE) != CONNECTION_TYPE_BLUETOOTH:
        return

    mac = entry.data.get(CONF_BT_MAC, "")
    if not mac:
        return

    async_add_entities([BluetoothPrinterBatterySensor(entry, mac)], update_before_add=True)


class BluetoothPrinterBatterySensor(SensorEntity):
    """Battery percentage for a paired BT printer (when bluez exposes it)."""

    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    # Battery level changes slowly; HA's default 30s isn't worth the D-Bus
    # round-trip cost. Update every 5 minutes.
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry, mac: str) -> None:
        self._entry = entry
        self._mac = mac
        self._attr_unique_id = f"{entry.entry_id}_battery"
        self._attr_available = False

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"ESC/POS Printer {self._entry.title}",
            manufacturer="ESC/POS",
            model="Bluetooth Printer",
        )

    async def async_update(self) -> None:
        """Poll bluez for the current battery percentage."""
        try:
            percentage = await query_bt_battery_percentage(self._mac)
        except Exception as exc:  # defensive; bluez can throw anything
            _LOGGER.debug(
                "Battery query failed for %s: %s", self._entry.entry_id, exc
            )
            self._attr_available = False
            return
        if percentage is None:
            # Either bluez doesn't track this device, or the device doesn't
            # expose Battery1 (typical for cheap thermal printers).
            self._attr_available = False
            self._attr_native_value = None
            return
        self._attr_available = True
        self._attr_native_value = percentage
