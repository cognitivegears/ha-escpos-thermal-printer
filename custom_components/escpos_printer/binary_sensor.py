from __future__ import annotations

from collections.abc import Callable
import contextlib
import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:  # type: ignore[no-untyped-def]
    adapter = hass.data[DOMAIN][entry.entry_id]["adapter"]
    entity = EscposOnlineSensor(hass, entry, adapter)
    async_add_entities([entity])


class EscposOnlineSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, adapter: Any) -> None:
        self._hass = hass
        self._entry = entry
        self._adapter = adapter
        self._unsubscribe: Callable[[], None] | None = None
        self._attr_unique_id = f"{entry.entry_id}_online"
        # Set initial state from adapter if available
        status = adapter.get_status()
        if status is not None:
            self._attr_is_on = bool(status)

    @property
    def device_info(self) -> DeviceInfo:
        connection_type = self._entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
        model = "USB Printer" if connection_type == CONNECTION_TYPE_USB else "Network Printer"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"ESC/POS Printer {self._entry.title}",
            manufacturer="ESC/POS",
            model=model,
        )

    async def async_added_to_hass(self) -> None:
        # Subscribe to adapter status updates
        def _on_status(ok: bool) -> None:
            self._attr_is_on = bool(ok)
            self.async_write_ha_state()

        self._unsubscribe = self._adapter.add_status_listener(_on_status)
        # Do not trigger a network probe automatically to keep unit tests offline

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        diag = self._adapter.get_diagnostics()
        connection_type = self._entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)

        attrs = {
            "connection_type": connection_type,
            "last_check": diag.get("last_check"),
            "last_ok": diag.get("last_ok"),
            "last_error": diag.get("last_error"),
            "last_latency_ms": diag.get("last_latency_ms"),
            "last_error_reason": diag.get("last_error_reason"),
        }

        # Add connection-specific info
        if hasattr(self._adapter, "get_connection_info"):
            attrs["connection_info"] = self._adapter.get_connection_info()

        return attrs

    async def async_will_remove_from_hass(self) -> None:
        if self._unsubscribe:
            with contextlib.suppress(Exception):
                self._unsubscribe()
            self._unsubscribe = None
