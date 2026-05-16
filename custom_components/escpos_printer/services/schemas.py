"""Voluptuous schemas for ESC/POS printer services.

Each schema is registered via ``hass.services.async_register(..., schema=...)``
so HA validates user input **before** the handler runs. ``services.yaml``
selectors are purely a UI hint; without these schemas, REST / WebSocket /
Python-script callers bypass all validation. See the Bronze quality-scale
``action-setup`` rule for the requirement.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.notify import ATTR_MESSAGE, ATTR_TITLE
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from ..const import (
    ATTR_ALIGN,
    ATTR_ALIGN_CT,
    ATTR_AUTO_RESIZE,
    ATTR_AUTOCONTRAST,
    ATTR_BARCODE_HEIGHT,
    ATTR_BARCODE_WIDTH,
    ATTR_BC,
    ATTR_BOLD,
    ATTR_CENTER,
    ATTR_CHECK,
    ATTR_CHUNK_DELAY_MS,
    ATTR_CODE,
    ATTR_CUT,
    ATTR_DATA,
    ATTR_DITHER,
    ATTR_DURATION,
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FALLBACK_IMAGE,
    ATTR_FEED,
    ATTR_FONT,
    ATTR_FORCE_SOFTWARE,
    ATTR_FRAGMENT_HEIGHT,
    ATTR_HEIGHT,
    ATTR_HIGH_DENSITY,
    ATTR_IMAGE,
    ATTR_IMAGE_WIDTH,
    ATTR_IMPL,
    ATTR_INVERT,
    ATTR_LINES,
    ATTR_MIRROR,
    ATTR_MODE,
    ATTR_POS,
    ATTR_ROTATION,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_THRESHOLD,
    ATTR_TIMES,
    ATTR_UNDERLINE,
    ATTR_WIDTH,
    DEFAULT_DITHER,
    DEFAULT_THRESHOLD,
    DITHER_MODES,
    IMPL_MODES,
    ROTATION_VALUES,
)
from ..security import (
    IMAGE_CHUNK_DELAY_MAX,
    IMAGE_CHUNK_DELAY_MIN,
    IMAGE_FRAGMENT_MAX,
    IMAGE_FRAGMENT_MIN,
    IMAGE_THRESHOLD_MAX,
    IMAGE_THRESHOLD_MIN,
    IMAGE_WIDTH_MAX,
    IMAGE_WIDTH_MIN,
    MAX_BARCODE_LENGTH,
    MAX_BASE64_INPUT_BYTES,
    MAX_FEED_LINES,
    MAX_QR_DATA_LENGTH,
    MAX_TEXT_LENGTH,
)

# `device_id` is a free-form field used by handlers to target a specific
# entry (or all entries when omitted). Accept str or [str] to match the
# `selector: device:` and `selector: device: multiple: true` UI shapes.
_DEVICE_ID = vol.Any(cv.string, [cv.string])

# Alignment / underline / cut / size enums shared across services.
_ALIGN = vol.In(["left", "center", "right"])
_UNDERLINE = vol.In(["none", "single", "double"])
_CUT = vol.In(["none", "partial", "full"])

# Width/height accept "normal"|"double"|"triple" or a number 1-8 (the
# UI surfaces both forms). Coerce numeric strings before checking the
# integer range.
_TEXT_SIZE = vol.Any(
    vol.In(["normal", "double", "triple"]),
    vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
)

_FEED = vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_FEED_LINES))

def _image_source_validator(value: Any) -> Any:
    """Length-cap an image source string before delegating to ``cv.template``.

    ``cv.template`` happily accepts megabyte strings (it constructs a
    Template object), which would defeat the pre-decode size cap in
    ``security.validate_base64_image``. Enforce the cap up front so a
    200 MB base64 string fails at the schema layer.
    """
    if isinstance(value, str) and len(value) > MAX_BASE64_INPUT_BYTES:
        raise vol.Invalid(
            f"image source too large (max ~{MAX_BASE64_INPUT_BYTES} chars)"
        )
    return cv.template(value)


_IMAGE_SOURCE = _image_source_validator

def _image_option_fragment(prefix: str = "") -> dict[Any, Any]:
    """Build the image-option fragment keyed with an optional prefix.

    Notify uses ``image_`` to disambiguate from the surrounding text
    options; the plain service call uses bare keys. ``ATTR_IMAGE_WIDTH``
    is already namespaced (``image_width``) so it never gets a prefix.
    """
    def k(name: str) -> str:
        if not prefix or name == ATTR_IMAGE_WIDTH:
            return name
        return f"{prefix}{name}"

    # ``chunk_delay_ms`` deliberately has **no default** at the schema
    # layer so the adapter can substitute its per-transport default
    # (Network/USB: 0; Bluetooth: 50). Setting one here would penalize the
    # fast-transport majority with an extra 50 ms per slice for no reason.
    # ``fragment_height`` / ``impl`` also have no schema default so the
    # per-printer reliability profile (options flow) can pick them.
    return {
        vol.Optional(k(ATTR_HIGH_DENSITY), default=True): cv.boolean,
        vol.Optional(k(ATTR_ALIGN)): _ALIGN,
        vol.Optional(k(ATTR_IMAGE_WIDTH)): vol.All(
            vol.Coerce(int), vol.Range(min=IMAGE_WIDTH_MIN, max=IMAGE_WIDTH_MAX)
        ),
        vol.Optional(k(ATTR_ROTATION), default=0): vol.All(
            vol.Coerce(int), vol.In(ROTATION_VALUES)
        ),
        vol.Optional(k(ATTR_DITHER), default=DEFAULT_DITHER): vol.In(DITHER_MODES),
        vol.Optional(k(ATTR_THRESHOLD), default=DEFAULT_THRESHOLD): vol.All(
            vol.Coerce(int),
            vol.Range(min=IMAGE_THRESHOLD_MIN, max=IMAGE_THRESHOLD_MAX),
        ),
        vol.Optional(k(ATTR_IMPL)): vol.In(IMPL_MODES),
        vol.Optional(k(ATTR_CENTER), default=False): cv.boolean,
        vol.Optional(k(ATTR_AUTOCONTRAST), default=False): cv.boolean,
        vol.Optional(k(ATTR_INVERT), default=False): cv.boolean,
        vol.Optional(k(ATTR_MIRROR), default=False): cv.boolean,
        vol.Optional(k(ATTR_AUTO_RESIZE), default=False): cv.boolean,
        vol.Optional(k(ATTR_FALLBACK_IMAGE)): _IMAGE_SOURCE,
        vol.Optional(k(ATTR_FRAGMENT_HEIGHT)): vol.All(
            vol.Coerce(int),
            vol.Range(min=IMAGE_FRAGMENT_MIN, max=IMAGE_FRAGMENT_MAX),
        ),
        vol.Optional(k(ATTR_CHUNK_DELAY_MS)): vol.All(
            vol.Coerce(int),
            vol.Range(min=IMAGE_CHUNK_DELAY_MIN, max=IMAGE_CHUNK_DELAY_MAX),
        ),
    }


_IMAGE_OPTION_FRAGMENT_PLAIN = _image_option_fragment()
_IMAGE_OPTION_FRAGMENT_NOTIFY = {
    vol.Optional(ATTR_IMAGE): _IMAGE_SOURCE,
    **_image_option_fragment("image_"),
}


PRINT_TEXT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_BOLD): cv.boolean,
        vol.Optional(ATTR_UNDERLINE): _UNDERLINE,
        vol.Optional(ATTR_WIDTH): _TEXT_SIZE,
        vol.Optional(ATTR_HEIGHT): _TEXT_SIZE,
        vol.Optional(ATTR_ENCODING): cv.string,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


PRINT_TEXT_UTF8_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_BOLD): cv.boolean,
        vol.Optional(ATTR_UNDERLINE): _UNDERLINE,
        vol.Optional(ATTR_WIDTH): _TEXT_SIZE,
        vol.Optional(ATTR_HEIGHT): _TEXT_SIZE,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


PRINT_QR_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_DATA): vol.All(
            cv.string, vol.Length(min=1, max=MAX_QR_DATA_LENGTH)
        ),
        vol.Optional(ATTR_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=16)),
        vol.Optional(ATTR_EC): vol.In(["L", "M", "Q", "H"]),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


_PRINT_IMAGE_SCHEMA_DICT: dict[Any, Any] = {
    vol.Optional("device_id"): _DEVICE_ID,
    vol.Required(ATTR_IMAGE): _IMAGE_SOURCE,
    **_IMAGE_OPTION_FRAGMENT_PLAIN,
    vol.Optional(ATTR_CUT): _CUT,
    vol.Optional(ATTR_FEED): _FEED,
}
PRINT_IMAGE_SCHEMA = vol.Schema(_PRINT_IMAGE_SCHEMA_DICT)


# Focused convenience-service schemas — the source field constrains the
# selector to a single domain, so the UI can present an entity picker
# instead of the generic template selector. Internally these all funnel
# into the same ``handle_print_image`` logic.
def _entity_id_in_domain(domain: str):  # type: ignore[no-untyped-def]
    def _validate(value: Any) -> str:
        if not isinstance(value, str):
            raise vol.Invalid(f"{domain} entity must be a string")
        if not value.startswith(f"{domain}."):
            raise vol.Invalid(f"Expected entity_id in domain '{domain}'")
        return value
    return _validate


PRINT_CAMERA_SNAPSHOT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("camera_entity"): _entity_id_in_domain("camera"),
        **_IMAGE_OPTION_FRAGMENT_PLAIN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)

PRINT_IMAGE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("image_entity"): _entity_id_in_domain("image"),
        **_IMAGE_OPTION_FRAGMENT_PLAIN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)

PRINT_IMAGE_URL_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("url"): vol.All(cv.string, vol.Length(min=1, max=2000)),
        **_IMAGE_OPTION_FRAGMENT_PLAIN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)

PREVIEW_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_IMAGE): _IMAGE_SOURCE,
        vol.Optional("output_path"): cv.string,
        **_IMAGE_OPTION_FRAGMENT_PLAIN,
    }
)

CALIBRATION_PRINT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Optional(ATTR_CUT, default="full"): _CUT,
        vol.Optional(ATTR_FEED, default=2): _FEED,
    }
)


PRINT_BARCODE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_CODE): vol.All(
            cv.string, vol.Length(min=1, max=MAX_BARCODE_LENGTH)
        ),
        vol.Required(ATTR_BC): cv.string,
        vol.Optional(ATTR_BARCODE_HEIGHT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=255)
        ),
        vol.Optional(ATTR_BARCODE_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=2, max=6)
        ),
        vol.Optional(ATTR_POS): vol.In(["ABOVE", "BELOW", "BOTH", "OFF"]),
        vol.Optional(ATTR_FONT): vol.In(["A", "B"]),
        vol.Optional(ATTR_ALIGN_CT): cv.boolean,
        vol.Optional(ATTR_CHECK): cv.boolean,
        # ``force_software`` accepts bool, "true"/"false" strings, and the
        # python-escpos impl names ("graphics", "bitImageColumn",
        # "bitImageRaster"). The handler does the cleanup; here we only
        # restrict the shape.
        vol.Optional(ATTR_FORCE_SOFTWARE): vol.Any(
            cv.boolean,
            vol.In(["graphics", "bitImageColumn", "bitImageRaster"]),
        ),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


FEED_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_LINES): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_FEED_LINES)
        ),
    }
)


CUT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_MODE): vol.In(["full", "partial"]),
    }
)


BEEP_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Optional(ATTR_TIMES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional(ATTR_DURATION): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=10)
        ),
    }
)


# Schema for the notify entity's `print_message` action. Wrapped in
# `cv.make_entity_service_schema` by the notify platform itself, so we
# only export the inner dict here.
PRINT_MESSAGE_FIELDS: dict[Any, Any] = {
    vol.Required(ATTR_MESSAGE): vol.All(
        cv.string, vol.Length(max=MAX_TEXT_LENGTH)
    ),
    vol.Optional(ATTR_TITLE): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
    vol.Optional("align"): _ALIGN,
    vol.Optional("bold"): cv.boolean,
    vol.Optional("underline"): _UNDERLINE,
    vol.Optional("width"): _TEXT_SIZE,
    vol.Optional("height"): _TEXT_SIZE,
    vol.Optional("utf8"): cv.boolean,
    vol.Optional("encoding"): cv.string,
    vol.Optional("cut"): _CUT,
    vol.Optional("feed"): _FEED,
    **_IMAGE_OPTION_FRAGMENT_NOTIFY,
}


__all__ = [
    "BEEP_SCHEMA",
    "CALIBRATION_PRINT_SCHEMA",
    "CUT_SCHEMA",
    "FEED_SCHEMA",
    "PREVIEW_IMAGE_SCHEMA",
    "PRINT_BARCODE_SCHEMA",
    "PRINT_CAMERA_SNAPSHOT_SCHEMA",
    "PRINT_IMAGE_ENTITY_SCHEMA",
    "PRINT_IMAGE_SCHEMA",
    "PRINT_IMAGE_URL_SCHEMA",
    "PRINT_MESSAGE_FIELDS",
    "PRINT_QR_SCHEMA",
    "PRINT_TEXT_SCHEMA",
    "PRINT_TEXT_UTF8_SCHEMA",
]
