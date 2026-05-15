from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_IN_EP,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_STATUS_INTERVAL,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
)
from .printer import NetworkPrinterConfig, UsbPrinterConfig

if TYPE_CHECKING:
    from . import EscposConfigEntry

# Fields to redact in diagnostics output
# - CONF_HOST: network printer hostname/IP
# - "host": runtime host field
# - "connection_info": contains host:port for network printers
TO_REDACT = {CONF_HOST, "host", "connection_info"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EscposConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = dict(entry.data)
    options = dict(entry.options)

    # runtime_data may be missing if setup failed before reaching async_setup_entry.
    runtime_data = getattr(entry, "runtime_data", None)
    adapter = runtime_data.adapter if runtime_data is not None else None

    connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)

    runtime: dict[str, Any] = {}
    if adapter is not None:
        config = adapter.config

        # Common diagnostics
        runtime = {
            "status": adapter.get_status(),
            "diagnostics": adapter.get_diagnostics(),
            "connection_type": connection_type,
            "profile": config.profile,
            "codepage": config.codepage,
            "line_width": config.line_width,
            "keepalive": getattr(adapter, "_keepalive", None),
            "status_interval": getattr(adapter, "_status_interval", None),
        }

        # Connection-specific diagnostics
        if connection_type == CONNECTION_TYPE_USB and isinstance(config, UsbPrinterConfig):
            runtime["vendor_id"] = f"0x{config.vendor_id:04X}" if config.vendor_id else None
            runtime["product_id"] = f"0x{config.product_id:04X}" if config.product_id else None
            runtime["in_ep"] = f"0x{config.in_ep:02X}" if config.in_ep else None
            runtime["out_ep"] = f"0x{config.out_ep:02X}" if config.out_ep else None
        elif isinstance(config, NetworkPrinterConfig):
            runtime["host"] = config.host
            runtime["port"] = config.port

        # Add connection info if available
        if hasattr(adapter, "get_connection_info"):
            runtime["connection_info"] = adapter.get_connection_info()

    # Build entry data based on connection type
    if connection_type == CONNECTION_TYPE_USB:
        entry_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_VENDOR_ID: f"0x{data.get(CONF_VENDOR_ID, 0):04X}",
            CONF_PRODUCT_ID: f"0x{data.get(CONF_PRODUCT_ID, 0):04X}",
            CONF_IN_EP: f"0x{data.get(CONF_IN_EP, 0):02X}",
            CONF_OUT_EP: f"0x{data.get(CONF_OUT_EP, 0):02X}",
            CONF_CODEPAGE: data.get(CONF_CODEPAGE),
            CONF_PROFILE: data.get(CONF_PROFILE),
            CONF_LINE_WIDTH: data.get(CONF_LINE_WIDTH),
        }
    else:
        entry_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            CONF_HOST: data.get(CONF_HOST),
            CONF_PORT: data.get(CONF_PORT),
            CONF_CODEPAGE: data.get(CONF_CODEPAGE),
            CONF_PROFILE: data.get(CONF_PROFILE),
            CONF_LINE_WIDTH: data.get(CONF_LINE_WIDTH),
        }

    payload = {
        "entry": {
            "title": entry.title,
            "data": entry_data,
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
