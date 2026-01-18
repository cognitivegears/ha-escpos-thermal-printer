"""Service handlers for ESC/POS Thermal Printer integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_extract_config_entry_ids

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

from .const import (
    ATTR_ALIGN,
    ATTR_ALIGN_CT,
    ATTR_BARCODE_HEIGHT,
    ATTR_BARCODE_WIDTH,
    ATTR_BC,
    ATTR_BOLD,
    ATTR_CHECK,
    ATTR_CODE,
    ATTR_CUT,
    ATTR_DATA,
    ATTR_DURATION,
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FEED,
    ATTR_FONT,
    ATTR_FORCE_SOFTWARE,
    ATTR_HEIGHT,
    ATTR_HIGH_DENSITY,
    ATTR_IMAGE,
    ATTR_LINES,
    ATTR_MODE,
    ATTR_POS,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_TIMES,
    ATTR_UNDERLINE,
    ATTR_WIDTH,
    DOMAIN,
    SERVICE_BEEP,
    SERVICE_CUT,
    SERVICE_FEED,
    SERVICE_PRINT_BARCODE,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_TEXT,
    SERVICE_PRINT_TEXT_UTF8,
)
from .text_utils import transcode_to_codepage

_LOGGER = logging.getLogger(__name__)


async def _async_get_target_entries(
    call: ServiceCall,
) -> list[ConfigEntry]:
    """Extract target config entries from a service call.

    Uses Home Assistant's official async_extract_config_entry_ids helper to resolve
    device/entity/area targets to config entries, then filters to only include
    entries for this integration.

    Args:
        call: Service call with target information

    Returns:
        List of ConfigEntry objects to target

    Raises:
        ServiceValidationError: If no valid targets are found
    """
    hass = call.hass

    # Use the official HA helper to extract config entry IDs from targets
    target_entry_ids = await async_extract_config_entry_ids(call)

    # Filter to only include entries for our domain
    target_entries: list[ConfigEntry] = [
        loaded_entry
        for loaded_entry in hass.config_entries.async_loaded_entries(DOMAIN)
        if loaded_entry.entry_id in target_entry_ids
    ]

    # If no targets specified (empty target_entry_ids), fall back to all configured printers
    if not target_entry_ids:
        target_entries = list(hass.config_entries.async_loaded_entries(DOMAIN))

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
    return adapter, defaults, adapter._config


async def async_setup_services(hass: HomeAssistant) -> None:  # noqa: PLR0915
    """Set up services for ESC/POS printer integration.

    This should be called once from async_setup to register services globally.
    Services will resolve targets to the appropriate printer adapters.
    """

    async def _handle_print_text(call: ServiceCall) -> None:
        """Handle print_text service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: print_text for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                await adapter.print_text(
                    hass,
                    text=cv.string(call.data[ATTR_TEXT]),
                    align=call.data.get(ATTR_ALIGN, defaults.get("align")),
                    bold=call.data.get(ATTR_BOLD),
                    underline=call.data.get(ATTR_UNDERLINE),
                    width=call.data.get(ATTR_WIDTH),
                    height=call.data.get(ATTR_HEIGHT),
                    encoding=call.data.get(ATTR_ENCODING),
                    cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                    feed=call.data.get(ATTR_FEED),
                )
            except Exception as err:
                _LOGGER.exception("Service print_text failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_print_text_utf8(call: ServiceCall) -> None:
        """Handle print_text_utf8 service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: print_text_utf8 for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                text = cv.string(call.data[ATTR_TEXT])

                # Get the configured codepage for transcoding
                codepage = config.codepage or "CP437"

                # Transcode UTF-8 text to the target codepage with look-alike mapping
                transcoded_text = await call.hass.async_add_executor_job(
                    transcode_to_codepage, text, codepage
                )

                _LOGGER.debug(
                    "Transcoded text from UTF-8 to %s: %d -> %d chars",
                    codepage,
                    len(text),
                    len(transcoded_text),
                )

                await adapter.print_text(
                    hass,
                    text=transcoded_text,
                    align=call.data.get(ATTR_ALIGN, defaults.get("align")),
                    bold=call.data.get(ATTR_BOLD),
                    underline=call.data.get(ATTR_UNDERLINE),
                    width=call.data.get(ATTR_WIDTH),
                    height=call.data.get(ATTR_HEIGHT),
                    encoding=None,  # Don't override - let printer use configured codepage
                    cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                    feed=call.data.get(ATTR_FEED),
                )
            except Exception as err:
                _LOGGER.exception("Service print_text_utf8 failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_print_qr(call: ServiceCall) -> None:
        """Handle print_qr service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: print_qr for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                await adapter.print_qr(
                    hass,
                    data=cv.string(call.data[ATTR_DATA]),
                    size=call.data.get(ATTR_SIZE),
                    ec=call.data.get(ATTR_EC),
                    align=call.data.get(ATTR_ALIGN, defaults.get("align")),
                    cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                    feed=call.data.get(ATTR_FEED),
                )
            except Exception as err:
                _LOGGER.exception("Service print_qr failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_print_image(call: ServiceCall) -> None:
        """Handle print_image service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: print_image for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                await adapter.print_image(
                    hass,
                    image=cv.string(call.data[ATTR_IMAGE]),
                    high_density=call.data.get(ATTR_HIGH_DENSITY, True),
                    align=call.data.get(ATTR_ALIGN, defaults.get("align")),
                    cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                    feed=call.data.get(ATTR_FEED),
                )
            except Exception as err:
                _LOGGER.exception("Service print_image failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_feed(call: ServiceCall) -> None:
        """Handle feed service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, _, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: feed for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                await adapter.feed(hass, lines=int(call.data[ATTR_LINES]))
            except Exception as err:
                _LOGGER.exception("Service feed failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_cut(call: ServiceCall) -> None:
        """Handle cut service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, _, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: cut for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                await adapter.cut(hass, mode=cv.string(call.data[ATTR_MODE]))
            except Exception as err:
                _LOGGER.exception("Service cut failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_print_barcode(call: ServiceCall) -> None:
        """Handle print_barcode service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: print_barcode for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                fs = call.data.get(ATTR_FORCE_SOFTWARE)
                if isinstance(fs, str) and fs.lower() in ("true", "false"):
                    fs = fs.lower() == "true"
                await adapter.print_barcode(
                    hass,
                    code=cv.string(call.data[ATTR_CODE]),
                    bc=cv.string(call.data[ATTR_BC]),
                    height=int(call.data.get(ATTR_BARCODE_HEIGHT, 64)),
                    width=int(call.data.get(ATTR_BARCODE_WIDTH, 3)),
                    pos=call.data.get(ATTR_POS, "BELOW"),
                    font=call.data.get(ATTR_FONT, "A"),
                    align_ct=bool(call.data.get(ATTR_ALIGN_CT, True)),
                    check=bool(call.data.get(ATTR_CHECK, False)),
                    force_software=fs,
                    align=defaults.get("align"),
                    cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                    feed=call.data.get(ATTR_FEED),
                )
            except Exception as err:
                _LOGGER.exception("Service print_barcode failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    async def _handle_beep(call: ServiceCall) -> None:
        """Handle beep service call."""
        target_entries = await _async_get_target_entries(call)

        for entry in target_entries:
            try:
                adapter, _, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
                _LOGGER.debug(
                    "Service call: beep for entry %s, data=%s",
                    entry.entry_id,
                    dict(call.data),
                )
                await adapter.beep(
                    hass,
                    times=int(call.data.get(ATTR_TIMES, 2)),
                    duration=int(call.data.get(ATTR_DURATION, 4)),
                )
            except Exception as err:
                _LOGGER.exception("Service beep failed for entry %s", entry.entry_id)
                raise HomeAssistantError(str(err)) from err

    # Register all services
    hass.services.async_register(DOMAIN, SERVICE_PRINT_TEXT_UTF8, _handle_print_text_utf8)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT_UTF8)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_TEXT, _handle_print_text)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_QR, _handle_print_qr)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_QR)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_IMAGE, _handle_print_image)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_IMAGE)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_BARCODE, _handle_print_barcode)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_BARCODE)

    hass.services.async_register(DOMAIN, SERVICE_FEED, _handle_feed)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_FEED)

    hass.services.async_register(DOMAIN, SERVICE_CUT, _handle_cut)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_CUT)

    hass.services.async_register(DOMAIN, SERVICE_BEEP, _handle_beep)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_BEEP)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload services for ESC/POS printer integration.

    This should be called when the last config entry is unloaded.
    """
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_TEXT_UTF8)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_TEXT)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_QR)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_IMAGE)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_BARCODE)
    hass.services.async_remove(DOMAIN, SERVICE_FEED)
    hass.services.async_remove(DOMAIN, SERVICE_CUT)
    hass.services.async_remove(DOMAIN, SERVICE_BEEP)
    _LOGGER.debug("Unloaded all %s services", DOMAIN)
