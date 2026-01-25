"""Service registration and unregistration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant

from ..const import (
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
from .control_handlers import handle_beep, handle_cut, handle_feed
from .print_handlers import (
    handle_print_barcode,
    handle_print_image,
    handle_print_qr,
    handle_print_text,
    handle_print_text_utf8,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Set up services for ESC/POS printer integration.

    This should be called once from async_setup to register services globally.
    Services will resolve targets to the appropriate printer adapters.
    """
    # Register all services
    hass.services.async_register(DOMAIN, SERVICE_PRINT_TEXT_UTF8, handle_print_text_utf8)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT_UTF8)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_TEXT, handle_print_text)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_QR, handle_print_qr)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_QR)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_IMAGE, handle_print_image)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_IMAGE)

    hass.services.async_register(DOMAIN, SERVICE_PRINT_BARCODE, handle_print_barcode)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_BARCODE)

    hass.services.async_register(DOMAIN, SERVICE_FEED, handle_feed)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_FEED)

    hass.services.async_register(DOMAIN, SERVICE_CUT, handle_cut)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_CUT)

    hass.services.async_register(DOMAIN, SERVICE_BEEP, handle_beep)
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
