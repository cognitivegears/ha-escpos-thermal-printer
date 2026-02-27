from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.notify import (
    ATTR_MESSAGE,
    ATTR_TITLE,
    NotifyEntity,
    NotifyEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
import voluptuous as vol

from .const import DOMAIN
from .text_utils import transcode_to_codepage

_LOGGER = logging.getLogger(__name__)

SERVICE_PRINT_MESSAGE = "print_message"

# Schema for the custom entity service
SERVICE_PRINT_MESSAGE_SCHEMA = cv.make_entity_service_schema(
    {
        vol.Required(ATTR_MESSAGE): cv.string,
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional("align"): vol.In(["left", "center", "right"]),
        vol.Optional("bold"): cv.boolean,
        vol.Optional("underline"): vol.In(["none", "single", "double"]),
        vol.Optional("width"): vol.Any(
            vol.In(["normal", "double", "triple"]),
            vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
        ),
        vol.Optional("height"): vol.Any(
            vol.In(["normal", "double", "triple"]),
            vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
        ),
        vol.Optional("utf8"): cv.boolean,
        vol.Optional("encoding"): cv.string,
        vol.Optional("cut"): vol.In(["none", "partial", "full"]),
        vol.Optional("feed"): vol.All(vol.Coerce(int), vol.Range(min=0, max=10)),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:  # type: ignore[no-untyped-def]
    _LOGGER.debug("Setting up notify entity for entry %s", entry.entry_id)
    async_add_entities([EscposNotifyEntity(hass, entry)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_PRINT_MESSAGE,
        SERVICE_PRINT_MESSAGE_SCHEMA,
        "print_message",
    )


class EscposNotifyEntity(NotifyEntity):
    """Notification entity for ESC/POS thermal printer.

    Provides Home Assistant notification integration that prints messages
    to the configured thermal printer.

    Standard send_message supports message and title only.
    Use the print_message entity service for full formatting control
    (bold, underline, width, height, alignment, cut, feed).
    """

    _attr_has_entity_name = True
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the notification entity."""
        self._hass = hass
        self._entry = entry
        self._attr_name = f"ESC/POS Printer {entry.title}"
        self._attr_unique_id = f"{entry.entry_id}_notify"

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a notification message to the thermal printer.

        This is the standard HA notify interface (message + title only).
        For text formatting options, use the print_message entity service.
        """
        await self.print_message(message=message, title=title)

    async def print_message(self, **kwargs: Any) -> None:
        """Print a formatted message to the thermal printer.

        Supports all text formatting parameters: bold, underline,
        width, height, alignment, encoding, cut, and feed.
        """
        message = kwargs.get("message", "")
        title = kwargs.get("title")

        _LOGGER.debug(
            "print_message called: title=%s, message_len=%s, keys=%s",
            title,
            len(message or ""),
            list(kwargs.keys()),
        )
        defaults = self._hass.data[DOMAIN][self._entry.entry_id]["defaults"]
        adapter = self._hass.data[DOMAIN][self._entry.entry_id]["adapter"]

        text = f"{title}\n{message}" if title else message

        # UTF-8 transcoding (same logic as print_text_utf8 service)
        use_utf8 = kwargs.get("utf8", False)
        encoding = kwargs.get("encoding")
        if use_utf8:
            config = adapter.config
            codepage = config.codepage or "CP437"
            text = await self._hass.async_add_executor_job(
                transcode_to_codepage, text, codepage
            )
            encoding = None  # Let printer use configured codepage

        try:
            await adapter.print_text(
                self._hass,
                text=text,
                align=kwargs.get("align", defaults.get("align")),
                bold=kwargs.get("bold", False),
                underline=kwargs.get("underline", "none"),
                width=kwargs.get("width", "normal"),
                height=kwargs.get("height", "normal"),
                encoding=encoding,
                cut=kwargs.get("cut", defaults.get("cut")),
                feed=kwargs.get("feed", 0),
            )
        except Exception as err:  # Bubble up to notify error handling
            _LOGGER.error("print_message failed: %s", err)
            raise
