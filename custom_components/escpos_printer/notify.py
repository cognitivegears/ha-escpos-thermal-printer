from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.notify import (
    NotifyEntity,
    NotifyEntityFeature,
)
from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity import DeviceInfo

from .const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DOMAIN,
)
from .image_sources import extract_image_kwargs, render_template
from .security import sanitize_log_message
from .services.schemas import PRINT_MESSAGE_FIELDS
from .text_utils import transcode_to_codepage

if TYPE_CHECKING:
    from . import EscposConfigEntry

_LOGGER = logging.getLogger(__name__)

# Notify entities don't poll; this constant only governs entity update
# concurrency. Printer I/O serialization is enforced by the adapter's
# asyncio.Lock — not here.
PARALLEL_UPDATES = 0

SERVICE_PRINT_MESSAGE = "print_message"

# Schema for the custom entity service. The bulk of the field
# definitions live in ``services/schemas.py`` so they share bounds and
# defaults with the global service schema.
SERVICE_PRINT_MESSAGE_SCHEMA = cv.make_entity_service_schema(
    PRINT_MESSAGE_FIELDS
)


async def async_setup_entry(hass: HomeAssistant, entry: EscposConfigEntry, async_add_entities) -> None:  # type: ignore[no-untyped-def]
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
    (bold, underline, width, height, alignment, cut, feed) plus optional
    image attachment.
    """

    _attr_has_entity_name = True
    _attr_name = None
    _attr_supported_features = NotifyEntityFeature.TITLE

    def __init__(self, hass: HomeAssistant, entry: EscposConfigEntry) -> None:
        """Initialize the notification entity."""
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_notify"

    @property
    def device_info(self) -> DeviceInfo:
        connection_type = self._entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
        if connection_type == CONNECTION_TYPE_USB:
            model = "USB Printer"
        elif connection_type == CONNECTION_TYPE_BLUETOOTH:
            model = "Bluetooth Printer"
        else:
            model = "Network Printer"

        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=f"ESC/POS Printer {self._entry.title}",
            manufacturer="ESC/POS",
            model=model,
        )

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Send a notification message to the thermal printer."""
        await self.print_message(message=message, title=title)

    async def print_message(self, **kwargs: Any) -> None:
        """Print a formatted message — with optional image — to the printer."""
        message = kwargs.get("message", "")
        title = kwargs.get("title")

        _LOGGER.debug(
            "print_message called: title_set=%s, message_len=%d, keys=%s",
            title is not None,
            len(message or ""),
            list(kwargs.keys()),
        )
        defaults = self._entry.runtime_data.defaults
        adapter = self._entry.runtime_data.adapter

        text = f"{title}\n{message}" if title else message

        # UTF-8 transcoding (same logic as print_text_utf8 service).
        use_utf8 = kwargs.get("utf8", False)
        encoding = kwargs.get("encoding")
        if use_utf8:
            codepage = adapter.config.codepage or "CP437"
            text = await self._hass.async_add_executor_job(
                transcode_to_codepage, text, codepage
            )
            encoding = None  # Let printer use configured codepage

        # ``or`` (not ``dict.get(k, default)``) so an explicit ``None``
        # from voluptuous still falls back to the configured default.
        align = kwargs.get("align") or defaults.get("align")
        text_kwargs = {
            "text": text,
            "align": align,
            "bold": kwargs.get("bold", False),
            "underline": kwargs.get("underline", "none"),
            "width": kwargs.get("width", "normal"),
            "height": kwargs.get("height", "normal"),
            "encoding": encoding,
        }

        image_source_raw = kwargs.get("image")
        context: Context | None = kwargs.get("context")

        try:
            if image_source_raw is None:
                # Plain text-only path.
                await adapter.print_text(
                    self._hass,
                    cut=kwargs.get("cut") or defaults.get("cut"),
                    feed=kwargs.get("feed", 0),
                    **text_kwargs,
                )
                return

            image_source = render_template(self._hass, image_source_raw)
            image_kwargs = extract_image_kwargs(
                {**kwargs, "image": image_source}, defaults, prefix="image_",
            )
            await adapter.print_text_with_image(
                self._hass,
                text_kwargs=text_kwargs,
                image_kwargs=image_kwargs,
                cut=kwargs.get("cut") or defaults.get("cut"),
                feed=kwargs.get("feed", 0),
                context=context,
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(
                f"print_message failed: {sanitize_log_message(str(err))}"
            ) from err
