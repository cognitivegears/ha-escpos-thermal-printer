"""Capability reporting for device actions."""

from __future__ import annotations

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType
import voluptuous as vol

from ..capabilities import get_profile_cut_modes
from ..const import (
    ATTR_ALIGN,
    ATTR_BARCODE_HEIGHT,
    ATTR_BARCODE_WIDTH,
    ATTR_BC,
    ATTR_BOLD,
    ATTR_CODE,
    ATTR_CUT,
    ATTR_DATA,
    ATTR_DURATION,
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FEED,
    ATTR_HEIGHT,
    ATTR_HIGH_DENSITY,
    ATTR_IMAGE,
    ATTR_LINES,
    ATTR_MODE,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_TIMES,
    ATTR_UNDERLINE,
    ATTR_WIDTH,
    DOMAIN,
)
from .actions import _get_entry_id_from_device
from .constants import (
    ACTION_BEEP,
    ACTION_CUT,
    ACTION_FEED,
    ACTION_PRINT_BARCODE,
    ACTION_PRINT_IMAGE,
    ACTION_PRINT_QR,
    ACTION_PRINT_TEXT,
    ACTION_PRINT_TEXT_UTF8,
)


async def _get_profile_for_device(hass: HomeAssistant, device_id: str) -> str | None:
    """Resolve a device_id to its configured printer profile, if any.

    Returns ``None`` for an unknown device/entry (callers fall back to
    ``get_profile_cut_modes(None)``, which is unrestricted — same as
    today's behaviour).
    """
    entry_id = _get_entry_id_from_device(hass, device_id)
    if entry_id is None:
        return None
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or not hasattr(entry, "runtime_data"):
        return None
    profile: str | None = entry.runtime_data.adapter.config.profile
    return profile


async def async_get_actions(hass: HomeAssistant, device_id: str) -> list[dict[str, str]]:
    """List device actions for ESC/POS printers."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)

    if device is None:
        return []

    # Check if this device belongs to our domain
    if not any(identifier[0] == DOMAIN for identifier in device.identifiers):
        return []

    # Return all available actions
    return [
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_PRINT_TEXT_UTF8,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_PRINT_TEXT,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_PRINT_QR,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_PRINT_IMAGE,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_PRINT_BARCODE,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_FEED,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_CUT,
            CONF_DEVICE_ID: device_id,
        },
        {
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: ACTION_BEEP,
            CONF_DEVICE_ID: device_id,
        },
    ]


def _get_capabilities_schema(action_type: str, cut_modes: list[str]) -> dict[str, vol.Schema]:
    """Get the capabilities schema for an action type.

    ``cut_modes`` is the profile-gated list from ``get_profile_cut_modes``
    (always includes "none"); it caps the ``cut``/``mode`` selectors so a
    profile without ``paperFullCut`` doesn't offer "full" (and likewise for
    "partial").
    """
    # The standalone "Cut Paper" action always cuts, so "none" isn't a
    # valid mode there. Fall back to "partial" if the profile supports no
    # cutter at all, so the action's schema never has zero valid choices.
    mode_choices = [m for m in cut_modes if m != "none"] or ["partial"]
    capabilities_map = {
        ACTION_PRINT_TEXT_UTF8: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_TEXT): cv.string,
                    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
                    vol.Optional(ATTR_BOLD): cv.boolean,
                    vol.Optional(ATTR_UNDERLINE): vol.In(["none", "single", "double"]),
                    vol.Optional(ATTR_WIDTH): vol.In(["normal", "double", "triple"]),
                    vol.Optional(ATTR_HEIGHT): vol.In(["normal", "double", "triple"]),
                    vol.Optional(ATTR_CUT): vol.In(cut_modes),
                    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                }
            )
        },
        ACTION_PRINT_TEXT: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_TEXT): cv.string,
                    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
                    vol.Optional(ATTR_BOLD): cv.boolean,
                    vol.Optional(ATTR_UNDERLINE): vol.In(["none", "single", "double"]),
                    vol.Optional(ATTR_WIDTH): vol.In(["normal", "double", "triple"]),
                    vol.Optional(ATTR_HEIGHT): vol.In(["normal", "double", "triple"]),
                    vol.Optional(ATTR_ENCODING): cv.string,
                    vol.Optional(ATTR_CUT): vol.In(cut_modes),
                    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                }
            )
        },
        ACTION_PRINT_QR: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_DATA): cv.string,
                    vol.Optional(ATTR_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=16)),
                    vol.Optional(ATTR_EC): vol.In(["L", "M", "Q", "H"]),
                    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
                    vol.Optional(ATTR_CUT): vol.In(cut_modes),
                    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                }
            )
        },
        ACTION_PRINT_IMAGE: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_IMAGE): cv.string,
                    vol.Optional(ATTR_HIGH_DENSITY): cv.boolean,
                    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
                    vol.Optional(ATTR_CUT): vol.In(cut_modes),
                    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                }
            )
        },
        ACTION_PRINT_BARCODE: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_CODE): cv.string,
                    vol.Required(ATTR_BC): vol.In(
                        [
                            "EAN13",
                            "EAN8",
                            "JAN13",
                            "JAN8",
                            "UPC-A",
                            "UPC-E",
                            "CODE39",
                            "CODE93",
                            "CODE128",
                            "ITF",
                            "ITF14",
                            "CODABAR",
                        ]
                    ),
                    vol.Optional(ATTR_BARCODE_HEIGHT): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=255)
                    ),
                    vol.Optional(ATTR_BARCODE_WIDTH): vol.All(
                        vol.Coerce(int), vol.Range(min=2, max=6)
                    ),
                    vol.Optional(ATTR_CUT): vol.In(cut_modes),
                    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
                }
            )
        },
        ACTION_FEED: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_LINES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                }
            )
        },
        ACTION_CUT: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_MODE): vol.In(mode_choices),
                }
            )
        },
        ACTION_BEEP: {
            "extra_fields": vol.Schema(
                {
                    vol.Optional(ATTR_TIMES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                    vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
                }
            )
        },
    }
    return capabilities_map.get(action_type, {})


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    profile = await _get_profile_for_device(hass, config[CONF_DEVICE_ID])
    cut_modes = await hass.async_add_executor_job(get_profile_cut_modes, profile)
    return _get_capabilities_schema(config[CONF_TYPE], cut_modes)
