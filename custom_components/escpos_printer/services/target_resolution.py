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


def _all_loaded_entries_for_broadcast(
    call: ServiceCall, *, broadcast: bool, warn_implicit_broadcast: bool = True
) -> list[ConfigEntry]:
    """Resolve the "no device_id" target list: every loaded printer.

    ``broadcast: true`` is the explicit, silent form of this. Omitting both
    ``device_id`` and ``broadcast`` is kept for backward compatibility, but
    warns once per call (unless there's only one printer, which is
    unambiguous) so a caller who meant to target one printer notices
    instead of silently printing to every printer.

    ``warn_implicit_broadcast=False`` skips that warning for callers that
    require exactly one target and will raise their own, more specific
    error right after this returns (the preview services) -- otherwise the
    log would warn about a broadcast print that never actually happens.

    Split out of :func:`_async_get_target_entries` to keep that function's
    branch count under the ruff/pylint threshold (PLR0912).
    """
    hass = call.hass
    all_entries = list(hass.config_entries.async_loaded_entries(DOMAIN))
    if not all_entries:
        raise ServiceValidationError(
            "No valid ESC/POS printer targets found. Please select a printer device.",
            translation_domain=DOMAIN,
            translation_key="no_target_found",
        )
    if not broadcast and warn_implicit_broadcast and len(all_entries) > 1:
        _LOGGER.warning(
            "escpos_printer.%s: no device_id specified — printing to all %d configured "
            "printers. Set broadcast: true to make this explicit, or device_id to target "
            "one printer.",
            call.service,
            len(all_entries),
        )
    return all_entries


async def _async_get_target_entries(
    call: ServiceCall,
    *,
    warn_implicit_broadcast: bool = True,
) -> list[ConfigEntry]:
    """Extract target config entries from a service call.

    Resolves device_id field from service call data to config entries.
    The device_id can be a single device ID string or a list of device IDs.

    Args:
        call: Service call with device_id in data
        warn_implicit_broadcast: Whether an implicit (no device_id, no
            broadcast) multi-printer target logs a warning. Pass False for
            callers that require exactly one target and raise their own
            error immediately after -- see :func:`_all_loaded_entries_for_broadcast`.

    Returns:
        List of ConfigEntry objects to target

    Raises:
        ServiceValidationError: If no valid targets are found
    """
    hass = call.hass

    # Get device_id from service call data
    device_ids = call.data.get("device_id")
    # `broadcast` and `device_id` are mutually exclusive at the schema layer
    # (see schemas._reject_broadcast_with_device_id), so if device_id_list
    # ends up non-empty below, broadcast is guaranteed False.
    broadcast = call.data.get("broadcast", False)

    # Normalize to a list
    if device_ids is None:
        device_id_list: list[str] = []
    elif isinstance(device_ids, str):
        device_id_list = [device_ids]
    else:
        device_id_list = list(device_ids)

    # If no device_id specified, fall back to all configured printers
    if not device_id_list:
        return _all_loaded_entries_for_broadcast(
            call, broadcast=broadcast, warn_implicit_broadcast=warn_implicit_broadcast
        )

    # Resolve device IDs to config entries
    device_registry = dr.async_get(hass)
    target_entry_ids: set[str] = set()

    for device_id in device_id_list:
        device = device_registry.async_get(device_id)
        if device is None:
            _LOGGER.warning("Targeted device %s not found in registry; skipping", device_id)
            continue

        # Get config entry IDs from the device.
        # DeviceEntry.config_entries is deprecated in HA 2026.8 (removal 2027.8)
        # in favour of config_entry_id; our floor (2026.5) predates that
        # attribute, so prefer it only when present.
        entry_id = getattr(device, "config_entry_id", None)
        entry_ids = [entry_id] if entry_id else device.config_entries
        matched = False
        for config_entry_id in entry_ids:
            # Check if this config entry is for our domain
            entry = hass.config_entries.async_get_entry(config_entry_id)
            if entry and entry.domain == DOMAIN:
                target_entry_ids.add(config_entry_id)
                matched = True
        if not matched:
            _LOGGER.warning("Targeted device %s is not an ESC/POS printer; skipping", device_id)

    # Get the actual config entry objects
    loaded_entry_ids = {e.entry_id for e in hass.config_entries.async_loaded_entries(DOMAIN)}
    not_loaded = target_entry_ids - loaded_entry_ids
    if not_loaded:
        # An entry that resolved from a targeted device but isn't loaded
        # (setup failed / disabled) would otherwise be dropped silently,
        # making a multi-printer call look fully successful.
        _LOGGER.warning(
            "Skipping %d targeted ESC/POS printer(s) that are not currently loaded "
            "(setup failed or entry disabled): %s",
            len(not_loaded),
            sorted(not_loaded),
        )

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
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or not hasattr(entry, "runtime_data"):
        raise HomeAssistantError(f"Printer configuration not found for entry {entry_id}")

    runtime_data = entry.runtime_data
    adapter = runtime_data.adapter
    defaults = runtime_data.defaults
    return adapter, defaults, adapter.config
