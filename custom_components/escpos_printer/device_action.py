"""Device actions for ESC/POS Thermal Printer."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType, TemplateVarsType
import voluptuous as vol

from .const import (
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
from .text_utils import transcode_to_codepage

# Action types
ACTION_PRINT_TEXT_UTF8 = "print_text_utf8"
ACTION_PRINT_TEXT = "print_text"
ACTION_PRINT_QR = "print_qr"
ACTION_PRINT_IMAGE = "print_image"
ACTION_PRINT_BARCODE = "print_barcode"
ACTION_FEED = "feed"
ACTION_CUT = "cut"
ACTION_BEEP = "beep"

ACTION_TYPES = {
    ACTION_PRINT_TEXT_UTF8,
    ACTION_PRINT_TEXT,
    ACTION_PRINT_QR,
    ACTION_PRINT_IMAGE,
    ACTION_PRINT_BARCODE,
    ACTION_FEED,
    ACTION_CUT,
    ACTION_BEEP,
}

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

async def async_get_actions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, str]]:
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


def _get_entry_id_from_device(hass: HomeAssistant, device_id: str) -> str | None:
    """Get the config entry ID from a device ID."""
    device_registry = dr.async_get(hass)
    device = device_registry.async_get(device_id)

    if device is None:
        return None

    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            # The second element is the entry_id
            return identifier[1]

    return None


async def async_call_action_from_config(
    hass: HomeAssistant,
    config: ConfigType,
    variables: TemplateVarsType,
    context: Context | None,
) -> None:
    """Execute a device action."""
    action_type = config[CONF_TYPE]
    device_id = config[CONF_DEVICE_ID]

    entry_id = _get_entry_id_from_device(hass, device_id)
    if entry_id is None:
        raise ValueError(f"Device {device_id} not found")

    domain_data = hass.data.get(DOMAIN, {})
    entry_data = domain_data.get(entry_id)
    if entry_data is None:
        raise ValueError(f"No data found for entry {entry_id}")

    adapter = entry_data.get("adapter")
    if adapter is None:
        raise ValueError(f"No adapter found for entry {entry_id}")

    defaults = entry_data.get("defaults", {})

    # Execute the appropriate action
    if action_type == ACTION_PRINT_TEXT_UTF8:
        await _call_print_text_utf8(hass, adapter, defaults, config, entry_data)
    elif action_type == ACTION_PRINT_TEXT:
        await _call_print_text(hass, adapter, defaults, config)
    elif action_type == ACTION_PRINT_QR:
        await _call_print_qr(hass, adapter, defaults, config)
    elif action_type == ACTION_PRINT_IMAGE:
        await _call_print_image(hass, adapter, defaults, config)
    elif action_type == ACTION_PRINT_BARCODE:
        await _call_print_barcode(hass, adapter, defaults, config)
    elif action_type == ACTION_FEED:
        await adapter.feed(hass, lines=config[ATTR_LINES])
    elif action_type == ACTION_CUT:
        await adapter.cut(hass, mode=config[ATTR_MODE])
    elif action_type == ACTION_BEEP:
        await adapter.beep(
            hass,
            times=config.get(ATTR_TIMES, 2),
            duration=config.get(ATTR_DURATION, 4),
        )


async def _call_print_text_utf8(
    hass: HomeAssistant,
    adapter: Any,
    defaults: dict[str, Any],
    config: ConfigType,
    entry_data: dict[str, Any],
) -> None:
    """Execute print_text_utf8 action."""
    text = config[ATTR_TEXT]

    # Get the configured codepage for transcoding
    adapter_config = adapter._config
    codepage = adapter_config.codepage or "CP437"

    # Transcode UTF-8 text to the target codepage
    transcoded_text = await hass.async_add_executor_job(
        transcode_to_codepage, text, codepage
    )

    await adapter.print_text(
        hass,
        text=transcoded_text,
        align=config.get(ATTR_ALIGN, defaults.get("align")),
        bold=config.get(ATTR_BOLD),
        underline=config.get(ATTR_UNDERLINE),
        width=config.get(ATTR_WIDTH),
        height=config.get(ATTR_HEIGHT),
        encoding=None,
        cut=config.get(ATTR_CUT, defaults.get("cut")),
        feed=config.get(ATTR_FEED),
    )


async def _call_print_text(
    hass: HomeAssistant,
    adapter: Any,
    defaults: dict[str, Any],
    config: ConfigType,
) -> None:
    """Execute print_text action."""
    await adapter.print_text(
        hass,
        text=config[ATTR_TEXT],
        align=config.get(ATTR_ALIGN, defaults.get("align")),
        bold=config.get(ATTR_BOLD),
        underline=config.get(ATTR_UNDERLINE),
        width=config.get(ATTR_WIDTH),
        height=config.get(ATTR_HEIGHT),
        encoding=config.get(ATTR_ENCODING),
        cut=config.get(ATTR_CUT, defaults.get("cut")),
        feed=config.get(ATTR_FEED),
    )


async def _call_print_qr(
    hass: HomeAssistant,
    adapter: Any,
    defaults: dict[str, Any],
    config: ConfigType,
) -> None:
    """Execute print_qr action."""
    await adapter.print_qr(
        hass,
        data=config[ATTR_DATA],
        size=config.get(ATTR_SIZE),
        ec=config.get(ATTR_EC),
        align=config.get(ATTR_ALIGN, defaults.get("align")),
        cut=config.get(ATTR_CUT, defaults.get("cut")),
        feed=config.get(ATTR_FEED),
    )


async def _call_print_image(
    hass: HomeAssistant,
    adapter: Any,
    defaults: dict[str, Any],
    config: ConfigType,
) -> None:
    """Execute print_image action."""
    await adapter.print_image(
        hass,
        image=config[ATTR_IMAGE],
        high_density=config.get(ATTR_HIGH_DENSITY, True),
        align=config.get(ATTR_ALIGN, defaults.get("align")),
        cut=config.get(ATTR_CUT, defaults.get("cut")),
        feed=config.get(ATTR_FEED),
    )


async def _call_print_barcode(
    hass: HomeAssistant,
    adapter: Any,
    defaults: dict[str, Any],
    config: ConfigType,
) -> None:
    """Execute print_barcode action."""
    await adapter.print_barcode(
        hass,
        code=config[ATTR_CODE],
        bc=config[ATTR_BC],
        height=config.get(ATTR_BARCODE_HEIGHT, 64),
        width=config.get(ATTR_BARCODE_WIDTH, 3),
        pos="BELOW",
        font="A",
        align_ct=True,
        check=False,
        force_software=None,
        align=defaults.get("align"),
        cut=config.get(ATTR_CUT, defaults.get("cut")),
        feed=config.get(ATTR_FEED),
    )


def _get_capabilities_schema(action_type: str) -> dict[str, vol.Schema]:
    """Get the capabilities schema for an action type."""
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
                    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
                    vol.Optional(ATTR_FEED): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10)
                    ),
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
                    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
                    vol.Optional(ATTR_FEED): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10)
                    ),
                }
            )
        },
        ACTION_PRINT_QR: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_DATA): cv.string,
                    vol.Optional(ATTR_SIZE): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=16)
                    ),
                    vol.Optional(ATTR_EC): vol.In(["L", "M", "Q", "H"]),
                    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
                    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
                    vol.Optional(ATTR_FEED): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10)
                    ),
                }
            )
        },
        ACTION_PRINT_IMAGE: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_IMAGE): cv.string,
                    vol.Optional(ATTR_HIGH_DENSITY): cv.boolean,
                    vol.Optional(ATTR_ALIGN): vol.In(["left", "center", "right"]),
                    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
                    vol.Optional(ATTR_FEED): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10)
                    ),
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
                    vol.Optional(ATTR_CUT): vol.In(["none", "partial", "full"]),
                    vol.Optional(ATTR_FEED): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=10)
                    ),
                }
            )
        },
        ACTION_FEED: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_LINES): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=10)
                    ),
                }
            )
        },
        ACTION_CUT: {
            "extra_fields": vol.Schema(
                {
                    vol.Required(ATTR_MODE): vol.In(["full", "partial"]),
                }
            )
        },
        ACTION_BEEP: {
            "extra_fields": vol.Schema(
                {
                    vol.Optional(ATTR_TIMES): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=10)
                    ),
                    vol.Optional(ATTR_DURATION): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=10)
                    ),
                }
            )
        },
    }
    return capabilities_map.get(action_type, {})


async def async_get_action_capabilities(
    hass: HomeAssistant, config: ConfigType
) -> dict[str, vol.Schema]:
    """List action capabilities."""
    return _get_capabilities_schema(config[CONF_TYPE])
