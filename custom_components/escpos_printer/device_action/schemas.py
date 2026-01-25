"""Validation schemas for device actions."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

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
from .constants import (
    ACTION_BEEP,
    ACTION_CUT,
    ACTION_FEED,
    ACTION_PRINT_BARCODE,
    ACTION_PRINT_IMAGE,
    ACTION_PRINT_QR,
    ACTION_PRINT_TEXT,
    ACTION_PRINT_TEXT_UTF8,
    ACTION_TYPES,
)

# Base schema for all actions
_BASE_SCHEMA: dict[vol.Marker | str, Any] = {
    vol.Required(CONF_DOMAIN): DOMAIN,
    vol.Required(CONF_DEVICE_ID): str,
    vol.Required(CONF_TYPE): vol.In(ACTION_TYPES),
}

# Action-specific schemas
_PRINT_TEXT_UTF8_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_PRINT_TEXT_UTF8,
    vol.Required(ATTR_TEXT): cv.string,
    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
    vol.Optional(ATTR_BOLD): cv.boolean,
    vol.Optional(ATTR_UNDERLINE): vol.In(["none", "single", "double"]),
    vol.Optional(ATTR_WIDTH): vol.In(["normal", "double", "triple"]),
    vol.Optional(ATTR_HEIGHT): vol.In(["normal", "double", "triple"]),
    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
}

_PRINT_TEXT_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_PRINT_TEXT,
    vol.Required(ATTR_TEXT): cv.string,
    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
    vol.Optional(ATTR_BOLD): cv.boolean,
    vol.Optional(ATTR_UNDERLINE): vol.In(["none", "single", "double"]),
    vol.Optional(ATTR_WIDTH): vol.In(["normal", "double", "triple"]),
    vol.Optional(ATTR_HEIGHT): vol.In(["normal", "double", "triple"]),
    vol.Optional(ATTR_ENCODING): cv.string,
    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
}

_PRINT_QR_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_PRINT_QR,
    vol.Required(ATTR_DATA): cv.string,
    vol.Optional(ATTR_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=16)),
    vol.Optional(ATTR_EC): vol.In(["L", "M", "Q", "H"]),
    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
}

_PRINT_IMAGE_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_PRINT_IMAGE,
    vol.Required(ATTR_IMAGE): cv.string,
    vol.Optional(ATTR_HIGH_DENSITY): cv.boolean,
    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
}

_PRINT_BARCODE_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_PRINT_BARCODE,
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
    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
    vol.Optional(ATTR_FEED): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
}

_FEED_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_FEED,
    vol.Required(ATTR_LINES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
}

_CUT_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_CUT,
    vol.Required(ATTR_MODE): vol.In(["full", "partial"]),
}

_BEEP_SCHEMA: dict[vol.Marker | str, Any] = {
    **_BASE_SCHEMA,
    vol.Required(CONF_TYPE): ACTION_BEEP,
    vol.Optional(ATTR_TIMES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
}

ACTION_SCHEMA = vol.Any(
    vol.Schema(_PRINT_TEXT_UTF8_SCHEMA),
    vol.Schema(_PRINT_TEXT_SCHEMA),
    vol.Schema(_PRINT_QR_SCHEMA),
    vol.Schema(_PRINT_IMAGE_SCHEMA),
    vol.Schema(_PRINT_BARCODE_SCHEMA),
    vol.Schema(_FEED_SCHEMA),
    vol.Schema(_CUT_SCHEMA),
    vol.Schema(_BEEP_SCHEMA),
)
