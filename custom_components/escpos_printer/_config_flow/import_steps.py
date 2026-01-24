"""Import configuration steps mixin."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult

from ..capabilities import PROFILE_AUTO
from ..const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_IN_EP,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_IN_EP,
    DEFAULT_LINE_WIDTH,
    DEFAULT_OUT_EP,
    DEFAULT_TIMEOUT,
)
from .usb_helpers import _generate_usb_unique_id, _parse_vid_pid

_LOGGER = logging.getLogger(__name__)


class ImportFlowMixin:
    """Mixin providing YAML import step.

    This mixin expects to be used with a class that has the following attributes
    and methods (typically provided by ConfigFlow and other mixins):
    - hass: HomeAssistant instance
    - async_set_unique_id(): Set unique ID for the config entry
    - _abort_if_unique_id_configured(): Abort if ID already exists
    - async_abort(): Abort the flow
    - async_create_entry(): Create the config entry
    - async_step_network(): Handle network configuration step
    """

    # These attributes are expected from the main flow class
    hass: Any

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Support YAML import if provided.

        Args:
            user_input: YAML configuration data

        Returns:
            FlowResult
        """
        _LOGGER.debug("Config flow import step with input: %s", user_input)

        if not user_input:
            return await self.async_step_network(None)  # type: ignore[attr-defined,no-any-return]

        # Default to network type if not specified
        connection_type = user_input.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
        user_input[CONF_CONNECTION_TYPE] = connection_type

        if connection_type == CONNECTION_TYPE_USB:
            # USB YAML import - create entry directly if all required fields present
            raw_vid = user_input.get(CONF_VENDOR_ID)
            raw_pid = user_input.get(CONF_PRODUCT_ID)

            if not raw_vid or not raw_pid:
                _LOGGER.error("USB YAML import missing vendor_id or product_id")
                return self.async_abort(reason="invalid_usb_device")  # type: ignore[attr-defined,no-any-return]

            # Coerce VID/PID to integers - handle strings like "0x04b8", "04b8", or "1208"
            try:
                vendor_id = _parse_vid_pid(raw_vid)
                product_id = _parse_vid_pid(raw_pid)
            except (ValueError, TypeError) as ex:
                _LOGGER.error("USB YAML import invalid vendor_id or product_id: %s", ex)
                return self.async_abort(reason="invalid_usb_device")  # type: ignore[attr-defined,no-any-return]

            # Validate VID/PID range
            if not (0x0001 <= vendor_id <= 0xFFFF) or not (0x0001 <= product_id <= 0xFFFF):
                _LOGGER.error("USB YAML import VID/PID out of range: %s/%s", vendor_id, product_id)
                return self.async_abort(reason="invalid_usb_device")  # type: ignore[attr-defined,no-any-return]

            # Set unique ID only if serial_number provided (allows multiple identical printers)
            serial_number = user_input.get("serial_number")
            if serial_number:
                unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
                self._abort_if_unique_id_configured()  # type: ignore[attr-defined]
            # Note: Without serial_number, no unique_id is set - duplicates allowed

            # Build complete entry data with defaults
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: vendor_id,
                CONF_PRODUCT_ID: product_id,
                CONF_IN_EP: user_input.get(CONF_IN_EP, DEFAULT_IN_EP),
                CONF_OUT_EP: user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP),
                CONF_TIMEOUT: user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                CONF_PROFILE: user_input.get(CONF_PROFILE, PROFILE_AUTO),
                CONF_CODEPAGE: user_input.get(CONF_CODEPAGE, ""),
                CONF_LINE_WIDTH: user_input.get(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH),
                CONF_DEFAULT_ALIGN: user_input.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                CONF_DEFAULT_CUT: user_input.get(CONF_DEFAULT_CUT, DEFAULT_CUT),
            }

            title = f"USB Printer {vendor_id:04X}:{product_id:04X}"
            return self.async_create_entry(title=title, data=data)  # type: ignore[attr-defined,no-any-return]

        # Network import - use existing flow
        return await self.async_step_network(user_input)  # type: ignore[attr-defined,no-any-return]
