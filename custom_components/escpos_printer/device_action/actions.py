"""Action execution functions for device actions."""

from __future__ import annotations

from typing import Any

from homeassistant.const import CONF_DEVICE_ID, CONF_TYPE
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.typing import ConfigType, TemplateVarsType

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
from ..text_utils import transcode_to_codepage
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
