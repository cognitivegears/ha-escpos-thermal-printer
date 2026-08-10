from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BAUDRATE,
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DETECTED_MANUFACTURER,
    CONF_DETECTED_MODEL,
    CONF_IMPL,
    CONF_IN_EP,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_RFCOMM_CHANNEL,
    CONF_SERIAL_PORT,
    CONF_VENDOR_ID,
    CONF_WIDTH_PIXELS,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
)
from .printer import (
    BluetoothPrinterConfig,
    NetworkPrinterConfig,
    SerialPrinterConfig,
    UsbPrinterConfig,
)

if TYPE_CHECKING:
    from . import EscposConfigEntry

# Fields to redact in diagnostics output
# - CONF_HOST / "host": network printer hostname/IP
# - "mac" / CONF_BT_MAC: Bluetooth device address
# - CONF_SERIAL_PORT / "serial_port": serial port path or URL
# - "connection_info": contains host:port, BT MAC, or port path
# - "title": the default entry title embeds the host:port (network) or
#   the MAC (Bluetooth), so it would otherwise re-leak the very
#   identifiers the other keys redact. Diagnostics downloads are commonly
#   attached to public issues.
TO_REDACT = {
    CONF_HOST,
    "host",
    "mac",
    CONF_BT_MAC,
    CONF_SERIAL_PORT,
    "serial_port",
    "connection_info",
    "title",
}


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
        diag = adapter.get_diagnostics()
        # Surface image-pipeline stats as a sibling key for easier triage.
        image_pipeline = diag.pop("image_pipeline", None) if isinstance(diag, dict) else None
        runtime = {
            "status": adapter.get_status(),
            "diagnostics": diag,
            "image_pipeline": image_pipeline,
            "connection_type": connection_type,
            "profile": config.profile,
            "codepage": config.codepage,
            "line_width": config.line_width,
            "width_pixels": adapter.get_profile_pixel_width(),
            "default_impl": getattr(adapter, "default_impl", None),
            "profile_no_image_support": getattr(adapter, "profile_no_image_support", None),
            "keepalive": getattr(adapter, "_keepalive", None),
            "status_interval": getattr(adapter, "_status_interval", None),
        }

        # Connection-specific diagnostics
        if connection_type == CONNECTION_TYPE_USB and isinstance(config, UsbPrinterConfig):
            runtime["vendor_id"] = f"0x{config.vendor_id:04X}" if config.vendor_id else None
            runtime["product_id"] = f"0x{config.product_id:04X}" if config.product_id else None
            runtime["in_ep"] = f"0x{config.in_ep:02X}" if config.in_ep else None
            runtime["out_ep"] = f"0x{config.out_ep:02X}" if config.out_ep else None
        elif isinstance(config, BluetoothPrinterConfig):
            runtime["mac"] = config.mac
            runtime["rfcomm_channel"] = config.rfcomm_channel
        elif connection_type == CONNECTION_TYPE_SERIAL and isinstance(config, SerialPrinterConfig):
            runtime["serial_port"] = config.serial_port  # redacted by TO_REDACT
            runtime["baudrate"] = config.baudrate
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
            CONF_WIDTH_PIXELS: data.get(CONF_WIDTH_PIXELS),
            CONF_IMPL: data.get(CONF_IMPL),
        }
    elif connection_type == CONNECTION_TYPE_BLUETOOTH:
        entry_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
            CONF_BT_MAC: data.get(CONF_BT_MAC),
            CONF_RFCOMM_CHANNEL: data.get(CONF_RFCOMM_CHANNEL),
            CONF_CODEPAGE: data.get(CONF_CODEPAGE),
            CONF_PROFILE: data.get(CONF_PROFILE),
            CONF_LINE_WIDTH: data.get(CONF_LINE_WIDTH),
            CONF_WIDTH_PIXELS: data.get(CONF_WIDTH_PIXELS),
            CONF_IMPL: data.get(CONF_IMPL),
        }
    elif connection_type == CONNECTION_TYPE_SERIAL:
        entry_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: data.get(CONF_SERIAL_PORT),  # redacted by TO_REDACT
            CONF_BAUDRATE: data.get(CONF_BAUDRATE),
            CONF_CODEPAGE: data.get(CONF_CODEPAGE),
            CONF_PROFILE: data.get(CONF_PROFILE),
            CONF_LINE_WIDTH: data.get(CONF_LINE_WIDTH),
            CONF_WIDTH_PIXELS: data.get(CONF_WIDTH_PIXELS),
            CONF_IMPL: data.get(CONF_IMPL),
        }
    else:
        entry_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            CONF_HOST: data.get(CONF_HOST),
            CONF_PORT: data.get(CONF_PORT),
            CONF_CODEPAGE: data.get(CONF_CODEPAGE),
            CONF_PROFILE: data.get(CONF_PROFILE),
            CONF_LINE_WIDTH: data.get(CONF_LINE_WIDTH),
            CONF_WIDTH_PIXELS: data.get(CONF_WIDTH_PIXELS),
            CONF_IMPL: data.get(CONF_IMPL),
            CONF_DETECTED_MANUFACTURER: data.get(CONF_DETECTED_MANUFACTURER),
            CONF_DETECTED_MODEL: data.get(CONF_DETECTED_MODEL),
        }

    payload = {
        "entry": {
            "title": entry.title,
            "data": entry_data,
            # Dump every option rather than hand-picking keys: the options
            # flow writes several triage-relevant fields (serial chunk
            # size/delay, allow_local_image_urls, default_align/cut,
            # reliability_profile, ...) that a hand-picked subset kept
            # missing. async_redact_data below still strips anything
            # matching TO_REDACT (recursively), so this doesn't leak more
            # than the previous subset did.
            "options": options,
        },
        "runtime": runtime,
    }

    return async_redact_data(payload, TO_REDACT)
