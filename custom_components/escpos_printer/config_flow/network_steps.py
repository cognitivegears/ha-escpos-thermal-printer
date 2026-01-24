"""Network configuration steps mixin."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
import voluptuous as vol

from ..capabilities import (
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    get_profile_choices_dict,
)
from ..const import (
    CONF_CONNECTION_TYPE,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONNECTION_TYPE_NETWORK,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
)
from .network_helpers import _can_connect

_LOGGER = logging.getLogger(__name__)


class NetworkFlowMixin:
    """Mixin providing network configuration step.

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

    async def async_step_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle network printer configuration.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            _LOGGER.debug("Config flow network step input: %s", user_input)
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

            await self.async_set_unique_id(f"{host}:{port}")  # type: ignore[attr-defined]
            self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

            _LOGGER.debug(
                "Attempting connection test to %s:%s (timeout=%s)", host, port, timeout
            )
            ok = await self.hass.async_add_executor_job(_can_connect, host, port, timeout)
            if ok:
                _LOGGER.debug("Connection test succeeded for %s:%s", host, port)

                # Store data and determine next step
                profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                self._user_data = {
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_TIMEOUT: timeout,
                    CONF_PROFILE: profile,
                }

                # If custom profile selected, go to custom profile step
                if profile == PROFILE_CUSTOM:
                    return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

                # Otherwise go to codepage step
                return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

            _LOGGER.warning("Connection test failed for %s:%s", host, port)
            errors["base"] = "cannot_connect"

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )

        return self.async_show_form(step_id="network", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]
