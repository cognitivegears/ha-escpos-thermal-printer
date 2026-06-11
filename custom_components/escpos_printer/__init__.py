from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv

from .capabilities import PROFILE_AUTO, is_valid_profile
from .const import (
    CONF_ALLOW_LOCAL_IMAGE_URLS,
    CONF_BAUDRATE,
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_IN_EP,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_RELIABILITY_PROFILE,
    CONF_RFCOMM_CHANNEL,
    CONF_SERIAL_PORT,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
    DEFAULT_ALIGN,
    DEFAULT_ALLOW_LOCAL_IMAGE_URLS,
    DEFAULT_BAUDRATE,
    DEFAULT_CUT,
    DEFAULT_IN_EP,
    DEFAULT_LINE_WIDTH,
    DEFAULT_OUT_EP,
    DEFAULT_RFCOMM_CHANNEL,
    DOMAIN,
    RELIABILITY_PROFILE_AUTO,
    RELIABILITY_PROFILE_PRESETS,
)
from .printer import (
    BluetoothPrinterConfig,
    EscposPrinterAdapterBase,
    NetworkPrinterConfig,
    SerialPrinterConfig,
    UsbPrinterConfig,
    create_printer_adapter,
)
from .security import sanitize_log_message
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[str] = ["notify", "binary_sensor", "sensor"]

# Domain-level singleton flag for one-time service registration.
# Per-entry state lives on entry.runtime_data (see EscposRuntimeData).
DATA_SERVICES_REGISTERED = "services_registered"


@dataclass
class EscposRuntimeData:
    """Per-entry runtime data."""

    adapter: EscposPrinterAdapterBase
    defaults: dict[str, Any] = field(default_factory=dict)


type EscposConfigEntry = ConfigEntry[EscposRuntimeData]


def _shared_print_config(entry: EscposConfigEntry) -> dict[str, Any]:
    """Transport-independent print settings, resolved options-over-data.

    Uses ``options.get(key, data.get(key))`` rather than
    ``options.get(key) or data.get(key)`` so an explicitly-chosen empty
    value — codepage/profile ``""`` meaning *auto* — is honoured instead
    of silently snapping back to the original setup value. Shared by all
    three transports so the resolution rule lives in one place.
    """
    opt = entry.options
    data = entry.data
    return {
        "timeout": float(opt.get(CONF_TIMEOUT, data.get(CONF_TIMEOUT, 4.0))),
        "codepage": opt.get(CONF_CODEPAGE, data.get(CONF_CODEPAGE)),
        "profile": opt.get(CONF_PROFILE, data.get(CONF_PROFILE)),
        "line_width": int(opt.get(CONF_LINE_WIDTH, data.get(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH))),
        "allow_local_image_urls": bool(
            opt.get(CONF_ALLOW_LOCAL_IMAGE_URLS, DEFAULT_ALLOW_LOCAL_IMAGE_URLS)
        ),
    }




async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the ESC/POS Printer integration.

    This is called once when the integration is first loaded.
    Services are registered here so they're available for all config entries.
    """
    hass.data.setdefault(DOMAIN, {})
    # Pre-create ``<config>/fonts/`` so users can drop TTF/OTF files in
    # there and reference them via ``print_text_image.font_path`` without
    # editing ``allowlist_external_dirs`` in configuration.yaml. The
    # integration treats this one directory as locally trusted (see
    # ``services.print_handlers._is_font_path_allowed``).
    fonts_dir = Path(hass.config.path("fonts"))

    def _ensure_fonts_dir() -> None:
        fonts_dir.mkdir(parents=True, exist_ok=True)

    try:
        await hass.async_add_executor_job(_ensure_fonts_dir)
    except OSError as err:
        _LOGGER.debug("Could not pre-create fonts directory %s: %s", fonts_dir, err)
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
        _LOGGER.info("Migrating config entry %s from version 1 to 2", config_entry.entry_id)

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

        _LOGGER.info("Migration to v2 complete for entry %s", config_entry.entry_id)
        # Fall through to v2 -> v3 migration

    if config_entry.version == 2:
        _LOGGER.info("Migrating config entry %s from version 2 to 3", config_entry.entry_id)

        new_data = dict(config_entry.data)

        # Add connection_type for existing network printers
        new_data.setdefault(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=3,
            minor_version=0,
        )

        _LOGGER.info("Migration to v3 complete for entry %s", config_entry.entry_id)
        return True

    return True


async def async_setup_entry(hass: HomeAssistant, entry: EscposConfigEntry) -> bool:
    """Set up ESC/POS Printer from a config entry."""
    _LOGGER.debug("Setting up escpos_printer entry: %s", entry.entry_id)

    # Domain-level singleton state (services-registered flag) lives in
    # hass.data[DOMAIN]; per-entry state lives on entry.runtime_data.
    hass.data.setdefault(DOMAIN, {})

    # Register services once when the first config entry is set up
    if not hass.data[DOMAIN].get(DATA_SERVICES_REGISTERED):
        await async_setup_services(hass)
        hass.data[DOMAIN][DATA_SERVICES_REGISTERED] = True
        _LOGGER.debug("Registered global services for %s", DOMAIN)

    # Determine connection type and create appropriate config
    connection_type = entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)

    shared = _shared_print_config(entry)
    config: UsbPrinterConfig | NetworkPrinterConfig | BluetoothPrinterConfig | SerialPrinterConfig
    if connection_type == CONNECTION_TYPE_USB:
        config = UsbPrinterConfig(
            vendor_id=entry.data.get(CONF_VENDOR_ID, 0),
            product_id=entry.data.get(CONF_PRODUCT_ID, 0),
            in_ep=entry.data.get(CONF_IN_EP, DEFAULT_IN_EP),
            out_ep=entry.data.get(CONF_OUT_EP, DEFAULT_OUT_EP),
            **shared,
        )
    elif connection_type == CONNECTION_TYPE_BLUETOOTH:
        config = BluetoothPrinterConfig(
            mac=str(entry.data.get(CONF_BT_MAC, "")),
            rfcomm_channel=int(entry.data.get(CONF_RFCOMM_CHANNEL, DEFAULT_RFCOMM_CHANNEL)),
            **shared,
        )
    elif connection_type == CONNECTION_TYPE_SERIAL:
        config = SerialPrinterConfig(
            serial_port=str(entry.data.get(CONF_SERIAL_PORT, "")),
            baudrate=int(entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
            **shared,
        )
    else:
        config = NetworkPrinterConfig(
            host=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, 9100),
            **shared,
        )

    adapter = create_printer_adapter(config)

    reliability_profile = entry.options.get(CONF_RELIABILITY_PROFILE, RELIABILITY_PROFILE_AUTO)
    adapter.reliability_profile_defaults = dict(
        RELIABILITY_PROFILE_PRESETS.get(reliability_profile, {})
    )

    entry.runtime_data = EscposRuntimeData(
        adapter=adapter,
        defaults={
            "align": entry.options.get(CONF_DEFAULT_ALIGN, entry.data.get(CONF_DEFAULT_ALIGN)),
            "cut": entry.options.get(CONF_DEFAULT_CUT, entry.data.get(CONF_DEFAULT_CUT)),
        },
    )

    # Start adapter background tasks (keepalive/status)
    # Note: USB printers don't support keepalive, but the adapter handles this
    try:
        await adapter.start(
            hass,
            keepalive=bool(entry.options.get(CONF_KEEPALIVE, False)),
            status_interval=int(entry.options.get(CONF_STATUS_INTERVAL, 0)),
        )
    except Exception as err:
        # The only blocking work in start() is the initial keepalive
        # connect; a printer that's off/asleep at HA boot should retry
        # with backoff (ConfigEntryNotReady), not hard-fail the entry.
        # Sanitise the message so a host/MAC in the error doesn't leak.
        await adapter.stop(hass)
        raise ConfigEntryNotReady(
            f"Could not connect to printer: {sanitize_log_message(str(err))}"
        ) from err

    # Note: options changes are picked up automatically — the options flow
    # extends ``OptionsFlowWithReload``, which reloads the entry when the
    # options change (the integration reads them only here at setup).

    # Optionally disable platform forwarding (used by unit tests)
    platforms = PLATFORMS
    if os.environ.get("ESC_POS_DISABLE_PLATFORMS") == "1":
        platforms = []
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EscposConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading escpos_printer entry: %s", entry.entry_id)
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Stop adapter background tasks
        try:
            adapter = entry.runtime_data.adapter
            await adapter.stop(hass)
        except Exception:  # best effort on unload
            pass
        _LOGGER.debug("Unloaded entry %s", entry.entry_id)

        # If this was the last loaded config entry, tear down global services.
        other_loaded = [
            e
            for e in hass.config_entries.async_loaded_entries(DOMAIN)
            if e.entry_id != entry.entry_id
        ]
        domain_data = hass.data.get(DOMAIN)
        if not other_loaded and domain_data and domain_data.get(DATA_SERVICES_REGISTERED):
            await async_unload_services(hass)
            domain_data[DATA_SERVICES_REGISTERED] = False
            _LOGGER.debug("Unloaded global services for %s", DOMAIN)

    return unload_ok
