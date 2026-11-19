"""Button platform: Feed, Cut, Beep, Sample test print on the device page."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import DeviceInfo

from .const import CONF_BLE_PROFILE, DOMAIN
from .device import build_device_info
from .sample_print import async_print_sample
from .services._handler_utils import _wrap_unexpected

if TYPE_CHECKING:
    from . import EscposConfigEntry

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

# ponytail: fixed tear-off advance; make configurable only if someone asks
FEED_LINES = 3


async def async_setup_entry(  # type: ignore[no-untyped-def]
    hass: HomeAssistant, entry: EscposConfigEntry, async_add_entities
) -> None:
    buttons = [EscposFeedButton(hass, entry), EscposSamplePrintButton(hass, entry)]
    if CONF_BLE_PROFILE not in entry.data:
        buttons[1:1] = [EscposCutButton(hass, entry), EscposBeepButton(hass, entry)]
    async_add_entities(buttons)


class _EscposButton(ButtonEntity):
    _attr_has_entity_name = True

    def __init__(self, hass: HomeAssistant, entry: EscposConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_translation_key}"

    @property
    def device_info(self) -> DeviceInfo:
        return build_device_info(self._entry)

    @property
    def available(self) -> bool:
        """Report whether the current entry has a loaded printer adapter."""
        return hasattr(self._entry, "runtime_data")

    async def async_press(self) -> None:
        if self._entry.state is not ConfigEntryState.LOADED or not self.available:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="printer_entry_unavailable"
            )
        try:
            await self._press()
        except HomeAssistantError:
            raise
        except Exception as err:
            # Mirror the service-handler contract in _handler_utils._for_each_target:
            # log the full traceback, then raise a sanitised HomeAssistantError so
            # USB serials / BT MACs / local paths don't leak to the Frontend toast.
            _LOGGER.exception(
                "Button %s failed for entry %s",
                self._attr_translation_key,
                self._entry.entry_id,
            )
            raise _wrap_unexpected(err, str(self._attr_translation_key)) from err

    async def _press(self) -> None:
        raise NotImplementedError


class EscposFeedButton(_EscposButton):
    _attr_translation_key = "feed"

    async def _press(self) -> None:
        await self._entry.runtime_data.adapter.feed(self._hass, lines=FEED_LINES)


class EscposCutButton(_EscposButton):
    _attr_translation_key = "cut"

    async def _press(self) -> None:
        # A Cut button that does nothing reads as broken — "none" → full.
        mode = self._entry.runtime_data.defaults.get("cut") or "full"
        if mode == "none":
            mode = "full"
        await self._entry.runtime_data.adapter.cut(self._hass, mode=mode)


class EscposBeepButton(_EscposButton):
    _attr_translation_key = "beep"

    async def _press(self) -> None:
        await self._entry.runtime_data.adapter.beep(self._hass)


class EscposSamplePrintButton(_EscposButton):
    _attr_translation_key = "sample_print"

    async def _press(self) -> None:
        await async_print_sample(self._hass, self._entry)
