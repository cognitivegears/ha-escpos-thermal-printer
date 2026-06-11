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

# serial.tools.list_ports ships with serialx (our manifest dependency).
# HA installs requirements before loading the integration, so this import
# succeeds at runtime. The try/except guards tests that run without it.
try:
    from serial.tools.list_ports import comports as _comports
except ImportError:  # pragma: no cover
    _comports = None

# Sentinel submitted when the user chooses "Enter manually" in the picker.
_MANUAL_ENTRY = "__manual__"

# Baudrate choices presented in the dropdown. The dict maps the integer value
# to its display label so voluptuous can validate against the key.
_BAUDRATE_CHOICES: dict[int, str] = {
    9600: "9600",
    19200: "19200",
    38400: "38400",
    57600: "57600",
    115200: "115200",
}


def _get_serial_port_choices() -> dict[str, str]:
    """Return available serial ports as {device_path: display_label}.

    Uses serial.tools.list_ports (bundled with serialx) so all port types are
    included — USB-serial adapters, native COM/ttyS ports, etc.  Returns an
    empty dict when no ports are present or the library is unavailable.
    """
    if _comports is None:
        return {}  # pragma: no cover

    choices: dict[str, str] = {}
    for port in _comports():
        label = port.device
        if port.description and port.description.lower() != "n/a":
            label += f" — {port.description}"
        if port.serial_number:
            label += f" (s/n: {port.serial_number})"
        choices[port.device] = label
    return choices


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
        """Show a dropdown of discovered serial ports.

        Skips directly to the manual-entry step when no ports are found.
        The user can also choose "Enter manually" to type a path or URL.
        """
        port_choices = await self.hass.async_add_executor_job(_get_serial_port_choices)

        if not port_choices:
            return await self.async_step_serial_manual()

        if user_input is not None:
            selected = user_input.get(CONF_SERIAL_PORT, "")
            if selected == _MANUAL_ENTRY:
                return await self.async_step_serial_manual()
            self._user_data[CONF_SERIAL_PORT] = selected
            return await self.async_step_serial_config()

        picker_choices = dict(port_choices)
        picker_choices[_MANUAL_ENTRY] = "Enter manually"

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="serial",
            data_schema=vol.Schema(
                {vol.Required(CONF_SERIAL_PORT): vol.In(picker_choices)}
            ),
        )

    async def async_step_serial_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Accept a manually typed serial port path or URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = str(user_input.get(CONF_SERIAL_PORT, "")).strip()
            if not port:
                errors["base"] = "serial_port_not_found"
            else:
                self._user_data[CONF_SERIAL_PORT] = port
                return await self.async_step_serial_config()

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="serial_manual",
            data_schema=vol.Schema({vol.Required(CONF_SERIAL_PORT): str}),
            errors=errors,
        )

    async def async_step_serial_config(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure baud rate, timeout, and profile, then test the connection."""
        errors: dict[str, str] = {}
        port = self._user_data.get(CONF_SERIAL_PORT, "")

        if user_input is not None:
            baudrate = int(user_input.get(CONF_BAUDRATE, DEFAULT_BAUDRATE))
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
            profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)

            if baudrate not in _BAUDRATE_CHOICES:
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
                    self._user_data.update(
                        {
                            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
                            CONF_BAUDRATE: baudrate,
                            CONF_TIMEOUT: timeout,
                            CONF_PROFILE: profile,
                            "_printer_name": f"Serial {sanitize_log_message(port)}",
                        }
                    )
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
                vol.Optional(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(
                    _BAUDRATE_CHOICES
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="serial_config",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={"port": port},
        )
