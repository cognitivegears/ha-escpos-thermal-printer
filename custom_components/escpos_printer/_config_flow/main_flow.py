"""Main config flow for ESC/POS Thermal Printer integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
import voluptuous as vol

from ..const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DOMAIN,
)
from .import_steps import ImportFlowMixin
from .network_steps import NetworkFlowMixin
from .settings_steps import SettingsFlowMixin
from .usb_steps import UsbFlowMixin

_LOGGER = logging.getLogger(__name__)


class EscposConfigFlow(
    NetworkFlowMixin,
    UsbFlowMixin,
    SettingsFlowMixin,
    ImportFlowMixin,
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Config flow for ESC/POS Thermal Printer."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize config flow."""
        self._user_data: dict[str, Any] = {}
        self._discovered_printers: list[dict[str, Any]] = []
        self._all_usb_devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 1: Connection type selection.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        if user_input is not None:
            connection_type = user_input.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
            self._user_data[CONF_CONNECTION_TYPE] = connection_type

            if connection_type == CONNECTION_TYPE_USB:
                return await self.async_step_usb_select()
            return await self.async_step_network()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_NETWORK): vol.In(
                    {
                        CONNECTION_TYPE_NETWORK: "Network (TCP/IP)",
                        CONNECTION_TYPE_USB: "USB (Direct)",
                    }
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create options flow handler.

        Args:
            config_entry: Config entry to be configured

        Returns:
            Options flow handler instance
        """
        # Import here to avoid circular imports
        from .options_flow import EscposOptionsFlowHandler  # noqa: PLC0415

        return EscposOptionsFlowHandler(config_entry)
