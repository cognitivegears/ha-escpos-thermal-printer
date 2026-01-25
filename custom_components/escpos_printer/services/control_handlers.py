"""Control operation service handlers."""

from __future__ import annotations

import logging

from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from ..const import (
    ATTR_DURATION,
    ATTR_LINES,
    ATTR_MODE,
    ATTR_TIMES,
)
from .target_resolution import _async_get_target_entries, _get_adapter_and_defaults

_LOGGER = logging.getLogger(__name__)


async def handle_feed(call: ServiceCall) -> None:
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
            await adapter.feed(call.hass, lines=int(call.data[ATTR_LINES]))
        except Exception as err:
            _LOGGER.exception("Service feed failed for entry %s", entry.entry_id)
            raise HomeAssistantError(str(err)) from err


async def handle_cut(call: ServiceCall) -> None:
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
            await adapter.cut(call.hass, mode=cv.string(call.data[ATTR_MODE]))
        except Exception as err:
            _LOGGER.exception("Service cut failed for entry %s", entry.entry_id)
            raise HomeAssistantError(str(err)) from err


async def handle_beep(call: ServiceCall) -> None:
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
                call.hass,
                times=int(call.data.get(ATTR_TIMES, 2)),
                duration=int(call.data.get(ATTR_DURATION, 4)),
            )
        except Exception as err:
            _LOGGER.exception("Service beep failed for entry %s", entry.entry_id)
            raise HomeAssistantError(str(err)) from err
