"""Control operation service handlers."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import ServiceCall
from homeassistant.helpers import config_validation as cv

from ..const import (
    ATTR_DURATION,
    ATTR_LINES,
    ATTR_MODE,
    ATTR_TIMES,
)
from ._handler_utils import _for_each_target

_LOGGER = logging.getLogger(__name__)


async def handle_feed(call: ServiceCall) -> None:
    """Handle feed service call."""

    async def _body(entry: Any, adapter: Any, _defaults: Any, _config: Any) -> None:
        await adapter.feed(call.hass, lines=int(call.data[ATTR_LINES]))

    await _for_each_target(call, "feed", _body)


async def handle_cut(call: ServiceCall) -> None:
    """Handle cut service call."""

    async def _body(entry: Any, adapter: Any, _defaults: Any, _config: Any) -> None:
        await adapter.cut(call.hass, mode=cv.string(call.data[ATTR_MODE]))

    await _for_each_target(call, "cut", _body)


async def handle_beep(call: ServiceCall) -> None:
    """Handle beep service call."""

    async def _body(entry: Any, adapter: Any, _defaults: Any, _config: Any) -> None:
        await adapter.beep(
            call.hass,
            times=int(call.data.get(ATTR_TIMES, 2)),
            duration=int(call.data.get(ATTR_DURATION, 4)),
        )

    await _for_each_target(call, "beep", _body)
