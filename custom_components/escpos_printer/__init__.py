from __future__ import annotations

import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

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
    CONF_CODEPAGE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    DOMAIN,
    SERVICE_BEEP,
    SERVICE_CUT,
    SERVICE_FEED,
    SERVICE_PRINT_BARCODE,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_QR,
    SERVICE_PRINT_TEXT,
)
from .printer import EscposPrinterAdapter, PrinterConfig

_LOGGER = logging.getLogger(__name__)


PLATFORMS: list[str] = ["notify", "binary_sensor"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _LOGGER.debug("Setting up escpos_printer entry: %s", entry.entry_id)
    config = PrinterConfig(
        host=entry.data[CONF_HOST],
        port=entry.data.get(CONF_PORT, 9100),
        timeout=float(entry.options.get(CONF_TIMEOUT, entry.data.get(CONF_TIMEOUT, 4.0))),
        codepage=entry.options.get(CONF_CODEPAGE) or entry.data.get(CONF_CODEPAGE),
        profile=entry.options.get(CONF_PROFILE) or entry.data.get(CONF_PROFILE),
        line_width=int(entry.options.get(CONF_LINE_WIDTH, entry.data.get(CONF_LINE_WIDTH, 48))),
    )
    adapter = EscposPrinterAdapter(config)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
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

    async def _handle_print_text(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: print_text data=%s", dict(call.data))
        try:
            defaults = hass.data[DOMAIN][entry.entry_id]["defaults"]
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
            _LOGGER.exception("Service print_text failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    async def _handle_print_qr(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: print_qr data=%s", dict(call.data))
        try:
            defaults = hass.data[DOMAIN][entry.entry_id]["defaults"]
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
            _LOGGER.exception("Service print_qr failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    async def _handle_print_image(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: print_image data=%s", dict(call.data))
        try:
            defaults = hass.data[DOMAIN][entry.entry_id]["defaults"]
            await adapter.print_image(
                hass,
                image=cv.string(call.data[ATTR_IMAGE]),
                high_density=call.data.get(ATTR_HIGH_DENSITY, True),
                align=call.data.get(ATTR_ALIGN, defaults.get("align")),
                cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                feed=call.data.get(ATTR_FEED),
            )
        except Exception as err:
            _LOGGER.exception("Service print_image failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    async def _handle_feed(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: feed data=%s", dict(call.data))
        try:
            await adapter.feed(hass, lines=int(call.data[ATTR_LINES]))
        except Exception as err:
            _LOGGER.exception("Service feed failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    async def _handle_cut(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: cut data=%s", dict(call.data))
        try:
            await adapter.cut(hass, mode=cv.string(call.data[ATTR_MODE]))
        except Exception as err:
            _LOGGER.exception("Service cut failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    async def _handle_print_barcode(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: print_barcode data=%s", dict(call.data))
        try:
            defaults = hass.data[DOMAIN][entry.entry_id]["defaults"]
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
                # Disable strict checking by default to improve compatibility
                check=bool(call.data.get(ATTR_CHECK, False)),
                force_software=fs,
                align=defaults.get("align"),
                cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                feed=call.data.get(ATTR_FEED),
            )
        except Exception as err:
            _LOGGER.exception("Service print_barcode failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    async def _handle_beep(call: ServiceCall) -> None:
        _LOGGER.debug("Service call: beep data=%s", dict(call.data))
        try:
            await adapter.beep(
                hass,
                times=int(call.data.get(ATTR_TIMES, 2)),
                duration=int(call.data.get(ATTR_DURATION, 4)),
            )
        except Exception as err:
            _LOGGER.exception("Service beep failed: %s", err)
            raise HomeAssistantError(str(err)) from err

    # Register services under the integration domain
    hass.services.async_register(DOMAIN, SERVICE_PRINT_TEXT, _handle_print_text)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_TEXT)
    hass.services.async_register(DOMAIN, SERVICE_PRINT_QR, _handle_print_qr)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_QR)
    hass.services.async_register(DOMAIN, SERVICE_PRINT_IMAGE, _handle_print_image)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_IMAGE)
    hass.services.async_register(DOMAIN, SERVICE_FEED, _handle_feed)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_FEED)
    hass.services.async_register(DOMAIN, SERVICE_CUT, _handle_cut)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_CUT)
    hass.services.async_register(DOMAIN, SERVICE_PRINT_BARCODE, _handle_print_barcode)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_PRINT_BARCODE)
    hass.services.async_register(DOMAIN, SERVICE_BEEP, _handle_beep)
    _LOGGER.debug("Registered service %s.%s", DOMAIN, SERVICE_BEEP)

    # Optionally disable platform forwarding (used by unit tests)
    platforms = PLATFORMS
    if os.environ.get("ESC_POS_DISABLE_PLATFORMS") == "1":
        platforms = []
    await hass.config_entries.async_forward_entry_setups(entry, platforms)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
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
    return unload_ok
