"""Print operation service handlers."""

from __future__ import annotations

import logging

from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from ..const import (
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
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FEED,
    ATTR_FONT,
    ATTR_FORCE_SOFTWARE,
    ATTR_HEIGHT,
    ATTR_HIGH_DENSITY,
    ATTR_IMAGE,
    ATTR_POS,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_UNDERLINE,
    ATTR_WIDTH,
)
from ..text_utils import transcode_to_codepage
from .target_resolution import _async_get_target_entries, _get_adapter_and_defaults

_LOGGER = logging.getLogger(__name__)


async def handle_print_text(call: ServiceCall) -> None:
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
                call.hass,
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


async def handle_print_text_utf8(call: ServiceCall) -> None:
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
                call.hass,
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


async def handle_print_qr(call: ServiceCall) -> None:
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
                call.hass,
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


async def handle_print_image(call: ServiceCall) -> None:
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
                call.hass,
                image=cv.string(call.data[ATTR_IMAGE]),
                high_density=call.data.get(ATTR_HIGH_DENSITY, True),
                align=call.data.get(ATTR_ALIGN, defaults.get("align")),
                cut=call.data.get(ATTR_CUT, defaults.get("cut")),
                feed=call.data.get(ATTR_FEED),
            )
        except Exception as err:
            _LOGGER.exception("Service print_image failed for entry %s", entry.entry_id)
            raise HomeAssistantError(str(err)) from err


async def handle_print_barcode(call: ServiceCall) -> None:
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
                call.hass,
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
