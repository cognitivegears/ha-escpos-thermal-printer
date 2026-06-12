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
from homeassistant.exceptions import (
    HomeAssistantError,
    ServiceValidationError,
    Unauthorized,
)

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

    Single target: ``body`` runs directly and its ``HomeAssistantError``
    (with any ``translation_key`` / ``status`` context) propagates
    untouched; other exceptions are sanitised via :func:`_wrap_unexpected`.

    Multiple targets (an explicit ``device_id`` list, or a broadcast to
    every configured printer): each target is attempted even if an
    earlier one fails, so one offline printer doesn't silently skip the
    rest. Failures are collected and reported together afterwards, named
    by printer, with a count of how many succeeded — partial success is
    no longer hidden behind the first error.

    Authorization (``Unauthorized``) and validation
    (``ServiceValidationError``) failures are NOT aggregated: they
    propagate immediately with their status / translation context, so a
    permission denial on any target fails the whole call (fail-closed)
    rather than being downgraded into a generic "N of M failed" string.
    """
    target_entries = await _async_get_target_entries(call)

    if len(target_entries) == 1:
        entry = target_entries[0]
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: %s for entry %s", service_name, entry.entry_id)
            await body(entry, adapter, defaults, config)
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Service %s failed for entry %s", service_name, entry.entry_id)
            raise _wrap_unexpected(err, service_name) from err
        return

    failures: list[tuple[str, str]] = []
    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: %s for entry %s", service_name, entry.entry_id)
            await body(entry, adapter, defaults, config)
        except (Unauthorized, ServiceValidationError):
            # Auth/validation failures are not per-printer transport
            # hiccups — propagate immediately with context intact instead
            # of aggregating and continuing to other printers.
            raise
        except Exception as err:
            _LOGGER.exception("Service %s failed for entry %s", service_name, entry.entry_id)
            failures.append(
                (
                    sanitize_log_message(entry.title or entry.entry_id),
                    sanitize_log_message(str(err)),
                )
            )

    if failures:
        succeeded = len(target_entries) - len(failures)
        detail = "; ".join(f"{name} ({msg})" for name, msg in failures)
        raise HomeAssistantError(
            f"Service {service_name} failed for {len(failures)} of "
            f"{len(target_entries)} printers ({succeeded} succeeded): {detail}"
        )


__all__ = ["_for_each_target", "_wrap_unexpected"]
