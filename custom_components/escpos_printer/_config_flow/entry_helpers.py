"""Helper functions for creating config entries."""

from __future__ import annotations

from typing import Any

from ..const import (
    CONF_CONNECTION_TYPE,
    CONF_HOST,
    CONF_PORT,
    CONF_PRODUCT_ID,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
)


def generate_entry_title(data: dict[str, Any], user_data: dict[str, Any]) -> str:
    """Generate entry title based on connection type.

    Args:
        data: Final entry data
        user_data: User data containing _printer_name for USB

    Returns:
        Entry title string
    """
    connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
    if connection_type == CONNECTION_TYPE_USB:
        printer_name = user_data.get("_printer_name")
        if printer_name is not None:
            return str(printer_name)
        return f"USB Printer {data.get(CONF_VENDOR_ID, 0):04X}:{data.get(CONF_PRODUCT_ID, 0):04X}"
    return f"{data[CONF_HOST]}:{data[CONF_PORT]}"


def prepare_entry_data(user_data: dict[str, Any], extra_data: dict[str, Any]) -> dict[str, Any]:
    """Prepare final entry data by merging and cleaning.

    Args:
        user_data: Base user data from previous steps
        extra_data: Additional data from current step

    Returns:
        Cleaned entry data dict
    """
    data = {**user_data, **extra_data}
    # Remove internal keys
    data.pop("_printer_name", None)
    return data
