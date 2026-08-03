"""Serial port configuration steps mixin."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import SerialPortSelector
from homeassistant.helpers.typing import UNDEFINED, UndefinedType
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

# Baudrate choices presented in the dropdown. String keys are required because
# the HA frontend submits all dropdown values as strings; integer keys cause
# vol.In to fail ("9600" not in {9600, 19200, ...}).
_BAUDRATE_CHOICES: dict[str, str] = {
    "9600": "9600",
    "19200": "19200",
    "38400": "38400",
    "57600": "57600",
    "115200": "115200",
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

    async def async_step_serial(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure serial port, baud rate, timeout, and profile in one step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            port = str(user_input.get(CONF_SERIAL_PORT, "")).strip()
            # Convert to str first so the vol.In string-key check works for
            # both UI submissions (always strings) and unit tests (may be int).
            baudrate_str = str(user_input.get(CONF_BAUDRATE, str(DEFAULT_BAUDRATE)))
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
            profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)

            # Check membership before parsing -- a non-numeric baudrate_str
            # must hit the invalid_baudrate branch, not raise out of int().
            if baudrate_str in _BAUDRATE_CHOICES:
                baudrate = int(baudrate_str)
            else:
                baudrate = DEFAULT_BAUDRATE
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
                            CONF_SERIAL_PORT: port,
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
                vol.Required(CONF_SERIAL_PORT): SerialPortSelector(),
                vol.Optional(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): vol.In(
                    _BAUDRATE_CHOICES
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="serial",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_reconfigure_serial(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing serial printer entry.

        The port path *is* the unique_id for serial printers (device
        nodes can be reassigned across reboots), so changing it
        legitimately changes the unique_id -- same address-based pattern
        as :meth:`NetworkFlowMixin.async_step_reconfigure_network`.
        """
        reconfigure_entry = self._get_reconfigure_entry()  # type: ignore[attr-defined]
        errors: dict[str, str] = {}

        if user_input is not None:
            port = str(user_input.get(CONF_SERIAL_PORT, "")).strip()
            baudrate_str = str(user_input.get(CONF_BAUDRATE, str(DEFAULT_BAUDRATE)))
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

            # Check membership before parsing -- a non-numeric baudrate_str
            # must hit the invalid_baudrate branch, not raise out of int().
            if baudrate_str in _BAUDRATE_CHOICES:
                baudrate = int(baudrate_str)
            else:
                baudrate = DEFAULT_BAUDRATE
                errors["base"] = "invalid_baudrate"

            if not errors:
                # Raw ``_async_abort_entries_match`` is case-sensitive but
                # the unique_id is lower-cased -- look up by the would-be
                # normalised unique_id instead, mirroring the network
                # reconfigure guard, so e.g. "/dev/TTYUSB0" vs
                # "/dev/ttyUSB0" can't collide on unique_id undetected.
                new_unique_id = f"serial:{port.lower()}"
                colliding = self.hass.config_entries.async_entry_for_domain_unique_id(
                    self.handler,  # type: ignore[attr-defined]
                    new_unique_id,
                )
                if colliding is not None and colliding.entry_id != reconfigure_entry.entry_id:
                    return self.async_abort(reason="already_configured")  # type: ignore[attr-defined,no-any-return]

                ok, error_code, _err_no = await self.hass.async_add_executor_job(
                    _can_connect_serial, port, baudrate, timeout
                )
                if ok:
                    # Only follow the port to a new auto-generated title
                    # when the entry still carries the original
                    # auto-generated one -- a user's manual rename must
                    # never be clobbered.
                    title: str | UndefinedType = UNDEFINED
                    old_port = reconfigure_entry.data.get(CONF_SERIAL_PORT, "")
                    if reconfigure_entry.title == f"Serial {sanitize_log_message(old_port)}":
                        title = f"Serial {sanitize_log_message(port)}"
                    return self.async_update_reload_and_abort(  # type: ignore[attr-defined,no-any-return]
                        reconfigure_entry,
                        unique_id=new_unique_id,
                        title=title,
                        data_updates={
                            CONF_SERIAL_PORT: port,
                            CONF_BAUDRATE: baudrate,
                            CONF_TIMEOUT: timeout,
                        },
                    )
                errors["base"] = _serial_error_to_key(error_code)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_SERIAL_PORT): SerialPortSelector(),
                vol.Optional(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): vol.In(
                    _BAUDRATE_CHOICES
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
            }
        )
        suggested_values: dict[str, Any] = dict(user_input or reconfigure_entry.data)
        # CONF_BAUDRATE is stored as int, but the dropdown's options are the
        # string keys in _BAUDRATE_CHOICES -- an unconverted int suggestion
        # fails to preselect and a untouched submit silently falls back to
        # the schema default (9600) instead of the entry's real baudrate.
        if CONF_BAUDRATE in suggested_values:
            suggested_values[CONF_BAUDRATE] = str(suggested_values[CONF_BAUDRATE])
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="reconfigure_serial",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                data_schema, suggested_values
            ),
            errors=errors,
        )
