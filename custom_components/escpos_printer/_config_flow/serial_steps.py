"""Serial port configuration steps mixin."""

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
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_PROFILE,
    CONF_SERIAL_PORT,
    CONF_TIMEOUT,
    CONNECTION_TYPE_SERIAL,
    DEFAULT_BAUDRATE,
    DEFAULT_TIMEOUT,
)
from ..security import sanitize_log_message
from .serial_helpers import _can_connect_serial, _serial_error_to_key

_LOGGER = logging.getLogger(__name__)

# Baudrate choices presented in the dropdown. The dict maps the integer value
# to its display label so voluptuous can validate against the key.
_BAUDRATE_CHOICES: dict[int, str] = {
    9600: "9600",
    19200: "19200",
    38400: "38400",
    57600: "57600",
    115200: "115200",
}


class SerialFlowMixin:
    """Mixin providing serial port configuration steps.

    This mixin expects to be used with a class that has the following
    attributes and methods (typically provided by ConfigFlow and other mixins):
    - hass: HomeAssistant instance
    - _user_data: dict for storing flow data
    - async_set_unique_id(): Set unique ID for the config entry
    - _abort_if_unique_id_configured(): Abort if ID already exists
    - async_show_form(): Show a form to the user
    - async_step_codepage(): Handle codepage configuration step
    - async_step_custom_profile(): Handle custom profile step
    """

    hass: Any
    _user_data: dict[str, Any]

    async def async_step_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle serial printer configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(
                "Config flow serial input keys: %s",
                sorted(user_input.keys()),
            )
            port = str(user_input.get(CONF_SERIAL_PORT, "")).strip()
            baudrate = int(user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
            profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)

            if not port:
                errors["base"] = "serial_port_not_found"
            elif baudrate not in _BAUDRATE_CHOICES:
                errors["base"] = "invalid_baudrate"

            if not errors:
                await self.async_set_unique_id(  # type: ignore[attr-defined]
                    f"serial:{port.lower()}"
                )
                self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

                _LOGGER.debug(
                    "Attempting serial connection test to %s @ %s baud",
                    sanitize_log_message(port),
                    baudrate,
                )
                ok, error_code, _err_no = await self.hass.async_add_executor_job(
                    _can_connect_serial, port, baudrate, timeout
                )
                if ok:
                    self._user_data = {
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                        CONF_SERIAL_PORT: port,
                        CONF_BAUDRATE: baudrate,
                        CONF_TIMEOUT: timeout,
                        CONF_PROFILE: profile,
                        "_printer_name": f"Serial {sanitize_log_message(port)}",
                    }
                    if profile == PROFILE_CUSTOM:
                        return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]
                    return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

                _LOGGER.warning(
                    "Serial connection test failed for %s (code=%s)",
                    sanitize_log_message(port),
                    error_code,
                )
                errors["base"] = _serial_error_to_key(error_code)

        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)
        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): str,
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(
                    _BAUDRATE_CHOICES
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="serial", data_schema=data_schema, errors=errors
        )
