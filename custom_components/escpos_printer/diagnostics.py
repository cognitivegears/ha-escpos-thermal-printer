from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CODEPAGE,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_STATUS_INTERVAL,
    DOMAIN,
)

TO_REDACT = {CONF_HOST}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = dict(entry.data)
    options = dict(entry.options)

    store = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    adapter = store.get("adapter")

    runtime: dict[str, Any] = {}
    if adapter is not None:
        runtime = {
            "status": adapter.get_status(),
            "diagnostics": adapter.get_diagnostics(),
            "profile": getattr(getattr(adapter, "_config", None), "profile", None) if getattr(adapter, "_config", None) else None,
            "codepage": getattr(getattr(adapter, "_config", None), "codepage", None) if getattr(adapter, "_config", None) else None,
            "line_width": getattr(getattr(adapter, "_config", None), "line_width", None) if getattr(adapter, "_config", None) else None,
            "host": getattr(getattr(adapter, "_config", None), "host", None) if getattr(adapter, "_config", None) else None,
            "port": getattr(getattr(adapter, "_config", None), "port", None) if getattr(adapter, "_config", None) else None,
            "keepalive": getattr(adapter, "_keepalive", None),
            "status_interval": getattr(adapter, "_status_interval", None),
        }

    payload = {
        "entry": {
            "title": entry.title,
            "data": {
                CONF_HOST: data.get(CONF_HOST),
                CONF_PORT: data.get(CONF_PORT),
                CONF_CODEPAGE: data.get(CONF_CODEPAGE),
                CONF_PROFILE: data.get(CONF_PROFILE),
                CONF_LINE_WIDTH: data.get(CONF_LINE_WIDTH),
            },
            "options": {
                CONF_CODEPAGE: options.get(CONF_CODEPAGE),
                CONF_PROFILE: options.get(CONF_PROFILE),
                CONF_LINE_WIDTH: options.get(CONF_LINE_WIDTH),
                CONF_KEEPALIVE: options.get(CONF_KEEPALIVE),
                CONF_STATUS_INTERVAL: options.get(CONF_STATUS_INTERVAL),
            },
        },
        "runtime": runtime,
    }

    return async_redact_data(payload, TO_REDACT)

