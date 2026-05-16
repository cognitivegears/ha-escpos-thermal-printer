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

# Battery polling cadence is set by _attr_should_poll on the entity.
PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: Any
) -> None:
    """Add a battery sensor for Bluetooth printers and a last-print sensor.

    Network and USB printers don't have battery state to report — battery
    sensor only for the BT branch. The last-print diagnostic sensor is
    always added so users get a live view of the image pipeline.
    """
    sensors: list[SensorEntity] = [LastImagePrintSensor(entry)]

    if entry.data.get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_BLUETOOTH:
        mac = entry.data.get(CONF_BT_MAC, "")
        if mac:
            sensors.append(BluetoothPrinterBatterySensor(entry, mac))

    async_add_entities(sensors, update_before_add=True)


class LastImagePrintSensor(SensorEntity):
    """Diagnostic sensor exposing the last image-print outcome.

    State is the count of successful image prints since startup; the
    interesting per-print fields (source kind, decoded dims, slice
    count, last error class) ride along as attributes so users can
    build dashboards without parsing diagnostics downloads.
    """

    _attr_has_entity_name = True
    _attr_name = "Last image print"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = True
    _attr_icon = "mdi:image-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_last_image_print"

    @property
    def device_info(self) -> DeviceInfo:
        connection_type = self._entry.data.get(CONF_CONNECTION_TYPE)
        if connection_type == CONNECTION_TYPE_BLUETOOTH:
            model = "Bluetooth Printer"
        elif connection_type == "usb":
            model = "USB Printer"
        else:
            model = "Network Printer"
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"ESC/POS Printer {self._entry.title}",
            manufacturer="ESC/POS",
            model=model,
        )

    async def async_update(self) -> None:
        """Pull the in-memory ImageStats snapshot off the adapter."""
        runtime = getattr(self._entry, "runtime_data", None)
        adapter = getattr(runtime, "adapter", None) if runtime else None
        stats = getattr(adapter, "_image_stats", None)
        if stats is None:
            self._attr_available = False
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            return
        self._attr_available = True
        self._attr_native_value = stats.total_prints
        self._attr_extra_state_attributes = {
            "total_failures": stats.total_failures,
            "last_source_kind": stats.last_source_kind,
            "last_decoded_dims": list(stats.last_decoded_dims)
            if stats.last_decoded_dims
            else None,
            "last_decoded_bytes": stats.last_decoded_bytes,
            "last_slice_count": stats.last_slice_count,
            "last_error_class": stats.last_error_class,
        }


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
