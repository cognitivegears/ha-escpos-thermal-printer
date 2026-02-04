from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from .capabilities import PROFILE_AUTO, is_valid_profile
from .const import (
    CONF_CODEPAGE,
    CONF_CUPS_SERVER,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_PRINTER_NAME,
    CONF_PROFILE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_LINE_WIDTH,
    DOMAIN,
)
from .printer import EscposPrinterAdapter, PrinterConfig
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[str] = ["notify", "binary_sensor"]

# Track if services have been registered
DATA_SERVICES_REGISTERED = "services_registered"


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the ESC/POS Printer integration.

    This is called once when the integration is first loaded.
    Services are registered here so they're available for all config entries.
    """
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old config entries to new format.

    Args:
        hass: Home Assistant instance
        config_entry: Config entry to migrate

    Returns:
        True if migration successful
    """
    if config_entry.version == 1:
        _LOGGER.info(
            "Migrating config entry %s from version 1 to 2", config_entry.entry_id
        )

        new_data = dict(config_entry.data)

        # Profile: validate it exists
        old_profile = new_data.get(CONF_PROFILE, "")
        if old_profile and not is_valid_profile(old_profile):
            _LOGGER.warning(
                "Profile '%s' not found in database; keeping for compatibility",
                old_profile,
            )

        # Ensure all expected fields exist with defaults
        # Empty string for codepage means "auto-detect"
        new_data.setdefault(CONF_PROFILE, PROFILE_AUTO)
        new_data.setdefault(CONF_CODEPAGE, "")
        new_data.setdefault(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH)
        new_data.setdefault(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN)
        new_data.setdefault(CONF_DEFAULT_CUT, DEFAULT_CUT)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=2,
            minor_version=0,
        )

        _LOGGER.info("Migration complete for entry %s", config_entry.entry_id)
        return True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ESC/POS Printer from a config entry."""
    _LOGGER.debug("Setting up escpos_printer entry: %s", entry.entry_id)

    # Initialize domain data if needed
    hass.data.setdefault(DOMAIN, {})

    # Register services once when the first config entry is set up
    if not hass.data[DOMAIN].get(DATA_SERVICES_REGISTERED):
        await async_setup_services(hass)
        hass.data[DOMAIN][DATA_SERVICES_REGISTERED] = True
        _LOGGER.debug("Registered global services for %s", DOMAIN)

    config = PrinterConfig(
        printer_name=entry.data[CONF_PRINTER_NAME],
        cups_server=entry.data.get(CONF_CUPS_SERVER),
        timeout=float(entry.options.get(CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, 4.0))),
        codepage=entry.options.get(CONF_CODEPAGE) or entry.data.get(CONF_CODEPAGE),
        profile=entry.options.get(CONF_PROFILE) or entry.data.get(CONF_PROFILE),
        line_width=int(entry.options.get(CONF_LINE_WIDTH, entry.data.get(CONF_LINE_WIDTH, 48))),
    )
    adapter = EscposPrinterAdapter(config)

    hass.data[DOMAIN][entry.entry_id] = {
        "adapter": adapter,
        "defaults": {
            "align": entry.options.get(CONF_DEFAULT_ALIGN, entry.data.get(CONF_DEFAULT_ALIGN)),
            "cut": entry.options.get(CONF_DEFAULT_CUT, entry.data.get(CONF_DEFAULT_CUT)),
        },
    }

    # Start adapter background tasks (keepalive/status)
    await adapter.start(
        hass,
        keepalive=bool(entry.options.get(CONF_KEEPALIVE, False)),
        status_interval=int(entry.options.get(CONF_STATUS_INTERVAL, 0)),
    )

    # Optionally disable platform forwarding (used by unit tests)
    platforms = PLATFORMS
    if os.environ.get("ESC_POS_DISABLE_PLATFORMS") == "1":
        platforms = []
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading escpos_printer entry: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Stop adapter background tasks
        try:
            adapter = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("adapter")
            if adapter is not None:
                await adapter.stop()
        except Exception:  # best effort on unload
            pass
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)

        # Check if this was the last config entry (excluding our metadata keys)
        domain_data = hass.data.get(DOMAIN, {})
        remaining_entries = [
            key for key in domain_data
            if key != DATA_SERVICES_REGISTERED
        ]
        if not remaining_entries and domain_data.get(DATA_SERVICES_REGISTERED):
            await async_unload_services(hass)
            domain_data[DATA_SERVICES_REGISTERED] = False
            _LOGGER.debug("Unloaded global services for %s", DOMAIN)

    return unload_ok
