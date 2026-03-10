"""CUPS configuration steps mixin."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from ..capabilities import (
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    get_profile_choices_dict,
)
from ..const import (
    CONF_CONNECTION_TYPE,
    CONF_CUPS_SERVER,
    CONF_PRINTER_NAME,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONNECTION_TYPE_CUPS,
    DEFAULT_TIMEOUT,
)
from ..printer.cups_adapter import (
    get_cups_printers,
    is_cups_available,
    is_cups_printer_available,
)

_LOGGER = logging.getLogger(__name__)


class CupsFlowMixin:
    """Mixin providing CUPS configuration steps.

    This mixin expects to be used with a class that has the following attributes
    and methods (typically provided by ConfigFlow and other mixins):
    - hass: HomeAssistant instance
    - _user_data: dict for storing flow data
    - async_set_unique_id(): Set unique ID for the config entry
    - _abort_if_unique_id_configured(): Abort if ID already exists
    - async_show_form(): Show a form to the user
    - async_step_codepage(): Handle codepage configuration step
    - async_step_custom_profile(): Handle custom profile step
    """

    # These attributes are expected from the main flow class
    hass: Any
    _user_data: dict[str, Any]
    _cups_server: str | None

    async def async_step_cups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 1: CUPS server configuration.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Config flow CUPS step input: %s", user_input)
            cups_server = user_input.get(CONF_CUPS_SERVER, "").strip() or None
            self._cups_server = cups_server

            cups_available = await self.hass.async_add_executor_job(
                is_cups_available, cups_server
            )
            if cups_available:
                _LOGGER.debug(
                    "CUPS server '%s' is available", cups_server or "localhost"
                )
                return await self.async_step_cups_printer()  # type: ignore[no-any-return]

            _LOGGER.warning(
                "CUPS server '%s' not available", cups_server or "localhost"
            )
            errors["base"] = "cups_unavailable"

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_CUPS_SERVER, default=""): str,
            }
        )

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="cups", data_schema=data_schema, errors=errors
        )

    async def async_step_cups_printer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 2: CUPS printer selection.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}

        # Get available CUPS printers from the configured server
        try:
            available_printers = await self.hass.async_add_executor_job(
                get_cups_printers, self._cups_server
            )
        except Exception as e:
            _LOGGER.warning("Failed to enumerate CUPS printers: %s", e)
            available_printers = []

        if not available_printers and user_input is None:
            _LOGGER.warning(
                "No printers found on CUPS server '%s'",
                self._cups_server or "localhost",
            )
            errors["base"] = "no_printers"

        if user_input is not None:
            _LOGGER.debug("Config flow CUPS printer step input: %s", user_input)
            printer_name = user_input[CONF_PRINTER_NAME]
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

            # Include server in unique_id if specified
            unique_id = (
                f"cups_{self._cups_server}_{printer_name}"
                if self._cups_server
                else f"cups_{printer_name}"
            )
            await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
            self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

            ok = await self.hass.async_add_executor_job(
                is_cups_printer_available, printer_name, self._cups_server
            )
            if ok:
                _LOGGER.debug("CUPS printer '%s' is available", printer_name)

                profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                self._user_data = {
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS,
                    CONF_CUPS_SERVER: self._cups_server,
                    CONF_PRINTER_NAME: printer_name,
                    CONF_TIMEOUT: timeout,
                    CONF_PROFILE: profile,
                }

                if profile == PROFILE_CUSTOM:
                    return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

                return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

            _LOGGER.warning("CUPS printer '%s' not available", printer_name)
            errors["base"] = "cannot_connect"

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(
            get_profile_choices_dict
        )

        # Build printer choices from available CUPS printers
        if available_printers:
            printer_choices = {p: p for p in available_printers}
            printer_field: vol.Required | vol.Optional = vol.Required(CONF_PRINTER_NAME)
            printer_validator: Any = vol.In(printer_choices)
        else:
            printer_field = vol.Required(CONF_PRINTER_NAME)
            printer_validator = str

        data_schema = vol.Schema(
            {
                printer_field: printer_validator,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(
                    profile_choices
                ),
            }
        )

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="cups_printer",
            data_schema=data_schema,
            errors=errors,
        )
