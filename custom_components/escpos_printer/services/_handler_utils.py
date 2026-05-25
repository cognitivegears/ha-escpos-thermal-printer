"""Shared per-target dispatch + error-wrapping helpers for service handlers.

Every non-preview service handler iterates the resolved targets, looks
up its adapter, runs the service-specific body, and translates any
unexpected exception into a sanitised :class:`HomeAssistantError`. The
copy-paste of that skeleton across 14 handlers (Phase 1 Q-H4) was the
single largest driver of file length in ``print_handlers.py`` and the
mechanism by which ``control_handlers.py`` drifted off the
``HomeAssistantError`` re-raise + log-sanitise contract (Phase 1 Q-H3 /
Phase 2 S-H2). Centralising the loop here makes the contract a single
edit-site.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import ServiceCall
from homeassistant.exceptions import HomeAssistantError

from ..security import sanitize_log_message
from .target_resolution import _async_get_target_entries, _get_adapter_and_defaults

_LOGGER = logging.getLogger(__name__)


def _wrap_unexpected(err: Exception, service_name: str) -> HomeAssistantError:
    """Wrap a non-HA exception in a sanitised :class:`HomeAssistantError`.

    HA exceptions (``HomeAssistantError``, ``Unauthorized``,
    ``ServiceValidationError``) propagate untouched so the framework
    preserves their status / translation context. Everything else has
    its message run through :func:`sanitize_log_message` so OS paths,
    USB serials, BT MACs, and credentials from pyusb / pyserial /
    python-escpos / aiohttp don't leak into the HA Frontend toast.
    """
    return HomeAssistantError(f"Service {service_name} failed: {sanitize_log_message(str(err))}")


# Body signature: (entry, adapter, defaults, config) -> awaitable
TargetBody = Callable[[ConfigEntry, Any, dict[str, Any], Any], Awaitable[None]]


async def _for_each_target(
    call: ServiceCall,
    service_name: str,
    body: TargetBody,
) -> None:
    """Run ``body`` once per resolved target with consistent error wrapping.

    Resolves targets via :func:`_async_get_target_entries`, looks up the
    adapter / defaults / config for each, logs a debug line, then awaits
    ``body``. ``HomeAssistantError`` (and its subclasses) propagate
    untouched so the HA framework keeps any ``translation_key`` /
    ``status`` context. Everything else is logged with a traceback and
    re-raised through :func:`_wrap_unexpected`.
    """
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: %s for entry %s", service_name, entry.entry_id)
            await body(entry, adapter, defaults, config)
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Service %s failed for entry %s", service_name, entry.entry_id)
            raise _wrap_unexpected(err, service_name) from err


__all__ = ["_for_each_target", "_wrap_unexpected"]
