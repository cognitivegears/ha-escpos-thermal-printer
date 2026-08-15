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

from .capabilities import (
    PROFILE_AUTO,
    canonical_profile_key,
    is_valid_profile,
    pick_impl,
    profile_declares_no_images,
)
from .const import (
    CONF_ALLOW_LOCAL_IMAGE_URLS,
    CONF_BAUDRATE,
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_IMPL,
    CONF_IN_EP,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_RELIABILITY_PROFILE,
    CONF_RFCOMM_CHANNEL,
    CONF_SERIAL_PORT,
    CONF_SERIAL_WRITE_CHUNK_DELAY_MS,
    CONF_SERIAL_WRITE_CHUNK_SIZE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    CONF_VENDOR_ID,
    CONF_WIDTH_PIXELS,
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
    DEFAULT_SERIAL_WRITE_CHUNK_DELAY_MS,
    DEFAULT_SERIAL_WRITE_CHUNK_SIZE,
    DEFAULT_STATUS_INTERVAL_SERIAL,
    DOMAIN,
    IMPL_AUTO,
    IMPL_MODES,
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
    profile_width_issue_id,
)
from .security import sanitize_log_message
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[str] = ["notify", "binary_sensor", "sensor", "button"]

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
        "width_pixels": (
            int(raw_width)
            if (raw_width := opt.get(CONF_WIDTH_PIXELS, data.get(CONF_WIDTH_PIXELS)))
            else None
        ),
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
            minor_version=1,
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
            minor_version=1,
        )

        _LOGGER.info("Migration to v3 complete for entry %s", config_entry.entry_id)
        return True

    # Normalize entries already at version 3 created before MINOR_VERSION existed
    # (or otherwise left at minor_version 0) so they match the flow's MINOR_VERSION.
    if config_entry.version == 3 and config_entry.minor_version < 1:
        hass.config_entries.async_update_entry(config_entry, minor_version=1)

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
    # Resolve a stored clone alias to its bundled target *before* building
    # the printer config, so the adapter/python-escpos constructor only
    # ever sees real profile names. Executor: resolution loads the
    # capabilities YAML.
    shared["profile"] = await hass.async_add_executor_job(canonical_profile_key, shared["profile"])
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
            write_chunk_size=int(
                entry.options.get(CONF_SERIAL_WRITE_CHUNK_SIZE, DEFAULT_SERIAL_WRITE_CHUNK_SIZE)
            ),
            write_chunk_delay_ms=int(
                entry.options.get(
                    CONF_SERIAL_WRITE_CHUNK_DELAY_MS, DEFAULT_SERIAL_WRITE_CHUNK_DELAY_MS
                )
            ),
        )
    else:
        config = NetworkPrinterConfig(
            host=entry.data[CONF_HOST],
            port=entry.data.get(CONF_PORT, 9100),
            **shared,
        )

    adapter = create_printer_adapter(config)
    adapter.entry_id = entry.entry_id

    reliability_profile = entry.options.get(CONF_RELIABILITY_PROFILE, RELIABILITY_PROFILE_AUTO)
    adapter.reliability_profile_defaults = dict(
        RELIABILITY_PROFILE_PRESETS.get(reliability_profile, {})
    )

    entry_impl = entry.options.get(CONF_IMPL, entry.data.get(CONF_IMPL, IMPL_AUTO))
    if entry_impl in IMPL_MODES:
        adapter.default_impl = entry_impl
    else:
        adapter.default_impl = await hass.async_add_executor_job(pick_impl, shared["profile"])
    adapter.profile_no_image_support = await hass.async_add_executor_job(
        profile_declares_no_images, shared["profile"]
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
    # Serial defaults to a non-zero status_interval (see
    # DEFAULT_STATUS_INTERVAL_SERIAL); network/USB/Bluetooth stay at 0.
    # Network/USB already get an implicit health check from the paper-status
    # poll; Bluetooth's status check opens a real RFCOMM connection and many
    # cheap printers beep on every connect, so it stays opt-in. Only applied
    # when the user hasn't set the option themselves.
    default_status_interval = (
        DEFAULT_STATUS_INTERVAL_SERIAL if connection_type == CONNECTION_TYPE_SERIAL else 0
    )
    try:
        await adapter.start(
            hass,
            keepalive=bool(entry.options.get(CONF_KEEPALIVE, False)),
            status_interval=int(entry.options.get(CONF_STATUS_INTERVAL, default_status_interval)),
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
        except Exception as err:  # best effort on unload
            _LOGGER.debug(
                "Adapter stop failed for entry %s: %s",
                entry.entry_id,
                sanitize_log_message(str(err)),
            )
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


async def async_remove_entry(hass: HomeAssistant, entry: EscposConfigEntry) -> None:
    """Clean up entry-scoped repair issues when the entry is deleted.

    Without this, a profile_width_fallback issue filed for this entry
    (see EscposPrinterAdapterBase._raise_profile_width_repair_issue) would
    linger in the repairs UI forever, even after the printer itself is
    removed from Home Assistant.
    """
    try:
        from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

        ir.async_delete_issue(hass, DOMAIN, profile_width_issue_id(entry.entry_id))
        # Pre-1.0 issue ids were scoped by profile name (see
        # EscposPrinterAdapterBase._clear_profile_width_repair_issue);
        # mirror that legacy-id deletion here too so an issue filed under
        # the old scheme doesn't outlive the entry it was raised for.
        profile = entry.options.get(CONF_PROFILE, entry.data.get(CONF_PROFILE))
        if profile:
            ir.async_delete_issue(hass, DOMAIN, f"profile_width_fallback_{profile}")
    except Exception as err:  # best effort
        _LOGGER.debug(
            "Could not clean up repair issues for entry %s: %s",
            entry.entry_id,
            sanitize_log_message(str(err)),
        )
