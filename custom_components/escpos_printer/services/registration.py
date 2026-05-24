"""Service registration and unregistration."""

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant, SupportsResponse

from ..const import (
    DOMAIN,
    SERVICE_BEEP,
    SERVICE_CALIBRATION_PRINT,
    SERVICE_CUT,
    SERVICE_FEED,
    SERVICE_PREVIEW_BOX,
    SERVICE_PREVIEW_IMAGE,
    SERVICE_PREVIEW_TABLE,
    SERVICE_PRINT_BARCODE,
    SERVICE_PRINT_BOX,
    SERVICE_PRINT_CAMERA_SNAPSHOT,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_IMAGE_ENTITY,
    SERVICE_PRINT_IMAGE_PATH,
    SERVICE_PRINT_IMAGE_URL,
    SERVICE_PRINT_KVTABLE,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_SEPARATOR,
    SERVICE_PRINT_TABLE,
    SERVICE_PRINT_TEXT,
    SERVICE_PRINT_TEXT_IMAGE,
    SERVICE_PRINT_TEXT_UTF8,
)
from .control_handlers import handle_beep, handle_cut, handle_feed
from .print_handlers import (
    handle_calibration_print,
    handle_preview_box,
    handle_preview_image,
    handle_preview_table,
    handle_print_barcode,
    handle_print_box,
    handle_print_camera_snapshot,
    handle_print_image,
    handle_print_image_entity,
    handle_print_image_path,
    handle_print_image_url,
    handle_print_kvtable,
    handle_print_qr,
    handle_print_separator,
    handle_print_table,
    handle_print_text,
    handle_print_text_image,
    handle_print_text_utf8,
)
from .schemas import (
    BEEP_SCHEMA,
    CALIBRATION_PRINT_SCHEMA,
    CUT_SCHEMA,
    FEED_SCHEMA,
    PREVIEW_BOX_SCHEMA,
    PREVIEW_IMAGE_SCHEMA,
    PREVIEW_TABLE_SCHEMA,
    PRINT_BARCODE_SCHEMA,
    PRINT_BOX_SCHEMA,
    PRINT_CAMERA_SNAPSHOT_SCHEMA,
    PRINT_IMAGE_ENTITY_SCHEMA,
    PRINT_IMAGE_PATH_SCHEMA,
    PRINT_IMAGE_SCHEMA,
    PRINT_IMAGE_URL_SCHEMA,
    PRINT_KVTABLE_SCHEMA,
    PRINT_QR_SCHEMA,
    PRINT_SEPARATOR_SCHEMA,
    PRINT_TABLE_SCHEMA,
    PRINT_TEXT_IMAGE_SCHEMA,
    PRINT_TEXT_SCHEMA,
    PRINT_TEXT_UTF8_SCHEMA,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration's services globally.

    Each registration passes ``schema=`` so HA validates input *before*
    dispatch (Bronze quality-scale ``action-setup`` rule). REST,
    WebSocket, and Python-script callers therefore go through the same
    validation as the UI selectors.
    """
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_TEXT_UTF8,
        handle_print_text_utf8,
        schema=PRINT_TEXT_UTF8_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT_UTF8)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_TEXT,
        handle_print_text,
        schema=PRINT_TEXT_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_QR,
        handle_print_qr,
        schema=PRINT_QR_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_QR)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_IMAGE,
        handle_print_image,
        schema=PRINT_IMAGE_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_IMAGE)

    # Convenience services with focused selectors — same handler logic
    # underneath but with friendlier UI affordances (entity picker for
    # camera/image, plain text for URL).
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_CAMERA_SNAPSHOT,
        handle_print_camera_snapshot,
        schema=PRINT_CAMERA_SNAPSHOT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_IMAGE_ENTITY,
        handle_print_image_entity,
        schema=PRINT_IMAGE_ENTITY_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_IMAGE_URL,
        handle_print_image_url,
        schema=PRINT_IMAGE_URL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_IMAGE_PATH,
        handle_print_image_path,
        schema=PRINT_IMAGE_PATH_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIEW_IMAGE,
        handle_preview_image,
        schema=PREVIEW_IMAGE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CALIBRATION_PRINT,
        handle_calibration_print,
        schema=CALIBRATION_PRINT_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_BARCODE,
        handle_print_barcode,
        schema=PRINT_BARCODE_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_BARCODE)

    # Text-effects services. ``print_box``, ``print_table``,
    # ``print_separator``, and ``print_kvtable`` build a plain text
    # layout then ride on ``adapter.print_text`` (codepage transcoding
    # included). ``print_text_image`` renders text to a PIL canvas with
    # a bundled / user-supplied TTF, optionally rotates it, and
    # dispatches through the existing image pipeline.
    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_BOX,
        handle_print_box,
        schema=PRINT_BOX_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_BOX)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_TABLE,
        handle_print_table,
        schema=PRINT_TABLE_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TABLE)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_TEXT_IMAGE,
        handle_print_text_image,
        schema=PRINT_TEXT_IMAGE_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT_IMAGE)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_SEPARATOR,
        handle_print_separator,
        schema=PRINT_SEPARATOR_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_SEPARATOR)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PRINT_KVTABLE,
        handle_print_kvtable,
        schema=PRINT_KVTABLE_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_KVTABLE)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIEW_BOX,
        handle_preview_box,
        schema=PREVIEW_BOX_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PREVIEW_BOX)

    hass.services.async_register(
        DOMAIN,
        SERVICE_PREVIEW_TABLE,
        handle_preview_table,
        schema=PREVIEW_TABLE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PREVIEW_TABLE)

    hass.services.async_register(
        DOMAIN,
        SERVICE_FEED,
        handle_feed,
        schema=FEED_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_FEED)

    hass.services.async_register(
        DOMAIN,
        SERVICE_CUT,
        handle_cut,
        schema=CUT_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_CUT)

    hass.services.async_register(
        DOMAIN,
        SERVICE_BEEP,
        handle_beep,
        schema=BEEP_SCHEMA,
    )
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_BEEP)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unload all services when the last config entry is removed."""
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_TEXT_UTF8)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_TEXT)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_QR)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_IMAGE)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_CAMERA_SNAPSHOT)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_IMAGE_ENTITY)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_IMAGE_URL)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_IMAGE_PATH)
    hass.services.async_remove(DOMAIN, SERVICE_PREVIEW_IMAGE)
    hass.services.async_remove(DOMAIN, SERVICE_CALIBRATION_PRINT)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_BARCODE)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_BOX)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_TABLE)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_TEXT_IMAGE)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_SEPARATOR)
    hass.services.async_remove(DOMAIN, SERVICE_PRINT_KVTABLE)
    hass.services.async_remove(DOMAIN, SERVICE_PREVIEW_BOX)
    hass.services.async_remove(DOMAIN, SERVICE_PREVIEW_TABLE)
    hass.services.async_remove(DOMAIN, SERVICE_FEED)
    hass.services.async_remove(DOMAIN, SERVICE_CUT)
    hass.services.async_remove(DOMAIN, SERVICE_BEEP)
    _LOGGER.debug("Unloaded all %s services", DOMAIN)
