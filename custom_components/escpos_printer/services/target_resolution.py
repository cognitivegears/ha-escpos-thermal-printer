"""Service target resolution helpers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def _async_get_target_entries(
    call: ServiceCall,
) -> list[ConfigEntry]:
    """Extract target config entries from a service call.

    Resolves device_id field from service call data to config entries.
    The device_id can be a single device ID string or a list of device IDs.

    Args:
        call: Service call with device_id in data

    Returns:
        List of ConfigEntry objects to target

    Raises:
        ServiceValidationError: If no valid targets are found
    """
    hass = call.hass

    # Get device_id from service call data
    device_ids = call.data.get("device_id")

    # Normalize to a list
    if device_ids is None:
        device_id_list: list[str] = []
    elif isinstance(device_ids, str):
        device_id_list = [device_ids]
    else:
        device_id_list = list(device_ids)

    # If no device_id specified, fall back to all configured printers
    if not device_id_list:
        all_entries = list(hass.config_entries.async_loaded_entries(DOMAIN))
        if not all_entries:
            raise ServiceValidationError(
                "No valid ESC/POS printer targets found. Please select a printer device.",
                translation_domain=DOMAIN,
                translation_key="no_target_found",
            )
        return all_entries

    # Resolve device IDs to config entries
    device_registry = dr.async_get(hass)
    target_entry_ids: set[str] = set()

    for device_id in device_id_list:
        device = device_registry.async_get(device_id)
        if device is None:
            _LOGGER.warning("Device %s not found in registry", device_id)
            continue

        # Get config entry IDs from the device
        for config_entry_id in device.config_entries:
            # Check if this config entry is for our domain
            entry = hass.config_entries.async_get_entry(config_entry_id)
            if entry and entry.domain == DOMAIN:
                target_entry_ids.add(config_entry_id)

    # Get the actual config entry objects
    target_entries: list[ConfigEntry] = [
        loaded_entry
        for loaded_entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if loaded_entry.entry_id in target_entry_ids
    ]

    if not target_entries:
        raise ServiceValidationError(
            "No valid ESC/POS printer targets found. Please select a printer device.",
            translation_domain=DOMAIN,
            translation_key="no_target_found",
        )

    return target_entries


def _get_adapter_and_defaults(
    hass: HomeAssistant, entry_id: str
) -> tuple[Any, dict[str, Any], Any]:
    """Get the adapter, defaults, and config for a config entry.

    Args:
        hass: Home Assistant instance
        entry_id: Config entry ID

    Returns:
        Tuple of (adapter, defaults dict, printer config)

    Raises:
        HomeAssistantError: If entry data is not found
    """
    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry_id)

    if entry_data is None:
        raise HomeAssistantError(f"Printer configuration not found for entry {entry_id}")

    adapter = entry_data.get("adapter")
    if adapter is None:
        raise HomeAssistantError(f"Printer adapter not found for entry {entry_id}")

    defaults = entry_data.get("defaults", {})
    return adapter, defaults, adapter.config
