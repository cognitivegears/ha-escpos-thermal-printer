from __future__ import annotations

from collections.abc import Callable
import contextlib
from datetime import timedelta
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo, EntityCategory

from .const import CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK, CONNECTION_TYPE_USB
from .device import build_device_info

if TYPE_CHECKING:
    from . import EscposConfigEntry

_LOGGER = logging.getLogger(__name__)

# EscposOnlineSensor's status updates are pushed by the adapter's status
# listener, not polled -- EscposCoverOpenSensor below is the polled one
# (see its own SCAN_INTERVAL note).
PARALLEL_UPDATES = 0

# EscposOnlineSensor is push; EscposCoverOpenSensor polls at the same
# 5-minute cadence as the paper sensor (they share one connection via the
# adapter's freshness guard).
SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_entry(  # type: ignore[no-untyped-def]
    hass: HomeAssistant, entry: EscposConfigEntry, async_add_entities
) -> None:
    adapter = entry.runtime_data.adapter
    entities: list[BinarySensorEntity] = [EscposOnlineSensor(hass, entry, adapter)]
    # Cover status needs a real read channel (DLE EOT response); the
    # Bluetooth/serial transports are write-only — same gate as the
    # paper sensor in sensor.py.
    if entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK) in (
        CONNECTION_TYPE_NETWORK,
        CONNECTION_TYPE_USB,
    ):
        entities.append(EscposCoverOpenSensor(entry))
    async_add_entities(entities, update_before_add=True)


class EscposOnlineSensor(BinarySensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _unrecorded_attributes = frozenset(
        {
            "last_check",
            "last_ok",
            "last_error",
            "last_latency_ms",
            "last_error_reason",
            "connection_info",
        }
    )

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
        return build_device_info(self._entry)

    async def async_added_to_hass(self) -> None:
        # Subscribe to adapter status updates
        def _on_status(ok: bool) -> None:
            self._attr_is_on = bool(ok)
            self.async_write_ha_state()

        self._unsubscribe = self._adapter.add_status_listener(_on_status)
        # No probe triggered here: the adapter already ran a one-shot
        # initial probe during EscposPrinterAdapterBase.start() (before
        # this entity was even constructed), so __init__ above already
        # picked up a real status via adapter.get_status().

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


class EscposCoverOpenSensor(BinarySensorEntity):
    """Cover-open fault sensor via the ESC/POS DLE EOT n=2 query."""

    _attr_has_entity_name = True
    _attr_translation_key = "cover_open"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_should_poll = True

    def __init__(self, entry: ConfigEntry) -> None:
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_cover_open"
        self._attr_available = False

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry)

    async def async_update(self) -> None:
        runtime = getattr(self._entry, "runtime_data", None)
        adapter = getattr(runtime, "adapter", None) if runtime else None
        if adapter is None:
            self._attr_available = False
            self._attr_is_on = None
            return
        status = await adapter.get_cover_status(self.hass)
        if status is None:
            self._attr_available = False
            self._attr_is_on = None
            return
        self._attr_available = True
        self._attr_is_on = status
