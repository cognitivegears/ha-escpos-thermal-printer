from __future__ import annotations

import logging
import socket
from typing import Any

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from .const import (
    CODEPAGE_CHOICES,
    CONF_CODEPAGE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_LINE_WIDTH,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DOMAIN,
    LINE_WIDTH_CHOICES,
)

_LOGGER = logging.getLogger(__name__)


def _can_connect(host: str, port: int, timeout: float) -> bool:
    """Test TCP connectivity to a host and port.

    Args:
        host: Hostname or IP address to connect to
        port: Port number to connect to
        timeout: Connection timeout in seconds

    Returns:
        True if connection succeeds, False otherwise
    """
    try:
        # Using a raw socket here to validate TCP reachability
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class EscposConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step of the config flow.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            _LOGGER.debug("Config flow user step input: %s", user_input)
            host = user_input[CONF_HOST]
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            _LOGGER.debug("Attempting connection test to %s:%s (timeout=%s)", host, port, timeout)
            ok = await self.hass.async_add_executor_job(_can_connect, host, port, timeout)
            if ok:
                _LOGGER.debug("Connection test succeeded for %s:%s", host, port)
                data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_TIMEOUT: timeout,
                    CONF_CODEPAGE: user_input.get(CONF_CODEPAGE),
                    CONF_PROFILE: user_input.get(CONF_PROFILE),
                    CONF_LINE_WIDTH: user_input.get(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH),
                    CONF_DEFAULT_ALIGN: user_input.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                    CONF_DEFAULT_CUT: user_input.get(CONF_DEFAULT_CUT, DEFAULT_CUT),
                }
                _LOGGER.debug(
                    "Creating config entry for %s:%s with options: codepage=%s align=%s cut=%s",
                    host,
                    port,
                    data.get(CONF_CODEPAGE),
                    data.get(CONF_DEFAULT_ALIGN),
                    data.get(CONF_DEFAULT_CUT),
                )
                return self.async_create_entry(title=f"{host}:{port}", data=data)
            _LOGGER.warning("Connection test failed for %s:%s", host, port)
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_CODEPAGE): vol.In(CODEPAGE_CHOICES),
                vol.Optional(CONF_PROFILE): str,
                vol.Optional(CONF_LINE_WIDTH, default=DEFAULT_LINE_WIDTH): vol.In(LINE_WIDTH_CHOICES),
                vol.Optional(CONF_DEFAULT_ALIGN, default=DEFAULT_ALIGN): vol.In(["left", "center", "right"]),
                vol.Optional(CONF_DEFAULT_CUT, default=DEFAULT_CUT): vol.In(["none", "partial", "full"]),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_import(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # Support YAML import if provided
        _LOGGER.debug("Config flow import step with input: %s", user_input)
        return await self.async_step_user(user_input)

    @staticmethod
    def async_get_options_flow(config_entry: Any) -> Any:
        """Create options flow handler.
        
        Args:
            config_entry: Config entry to be configured
            
        Returns:
            Options flow handler instance
        """
        return EscposOptionsFlowHandler(config_entry)


class EscposOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: Any) -> None:
        """Initialize the options flow handler.
        
        Args:
            config_entry: Config entry to be configured (required for HA 2024.8-2024.10 compatibility)
        """
        # Store config_entry for HA 2024.8-2024.10 compatibility
        # HA 2024.11+ provides this automatically via base class property, but older versions require explicit storage
        # Use object.__setattr__ to bypass the read-only property in newer HA versions
        object.__setattr__(self, '_config_entry_compat', config_entry)
        super().__init__()
    
    @property
    def config_entry(self) -> Any:
        """Get config entry.
        
        Returns the config entry from the base class if available (HA 2024.11+),
        otherwise returns our stored copy (HA 2024.8-2024.10).
        """
        # Try to get from base class first (HA 2024.11+)
        try:
            return super().config_entry
        except AttributeError:
            # Fall back to our stored copy (HA 2024.8-2024.10)
            return self._config_entry_compat
    
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the options flow initialization.

        Args:
            user_input: User provided options data

        Returns:
            FlowResult containing the next step or final result
        """
        if user_input is not None:
            _LOGGER.debug("Options flow update for entry %s: %s", self.config_entry.entry_id, user_input)
            return self.async_create_entry(title="Options", data=user_input)

        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_TIMEOUT,
                    default=self.config_entry.options.get(
                        CONF_TIMEOUT, self.config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
                    ),
                ): vol.Coerce(float),
                vol.Optional(
                    CONF_CODEPAGE,
                    default=self.config_entry.options.get(
                        CONF_CODEPAGE, self.config_entry.data.get(CONF_CODEPAGE)
                    ) or CODEPAGE_CHOICES[0],
                ): vol.In(CODEPAGE_CHOICES),
                vol.Optional(
                    CONF_PROFILE,
                    default=self.config_entry.options.get(
                        CONF_PROFILE, self.config_entry.data.get(CONF_PROFILE, "")
                    ) or "",
                ): str,
                vol.Optional(
                    CONF_LINE_WIDTH,
                    default=self.config_entry.options.get(
                        CONF_LINE_WIDTH, self.config_entry.data.get(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH)
                    ),
                ): vol.In(LINE_WIDTH_CHOICES),
                vol.Optional(
                    CONF_DEFAULT_ALIGN,
                    default=self.config_entry.options.get(
                        CONF_DEFAULT_ALIGN,
                        self.config_entry.data.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                    ),
                ): vol.In(["left", "center", "right"]),
                vol.Optional(
                    CONF_DEFAULT_CUT,
                    default=self.config_entry.options.get(
                        CONF_DEFAULT_CUT, self.config_entry.data.get(CONF_DEFAULT_CUT, DEFAULT_CUT)
                    ),
                ): vol.In(["none", "partial", "full"]),
                vol.Optional(CONF_KEEPALIVE, default=self.config_entry.options.get(CONF_KEEPALIVE, False)): bool,
                vol.Optional(
                    CONF_STATUS_INTERVAL,
                    default=self.config_entry.options.get(CONF_STATUS_INTERVAL, 0),
                ): int,
            }
        )
        _LOGGER.debug("Showing options form for entry %s", self.config_entry.entry_id)
        return self.async_show_form(step_id="init", data_schema=data_schema)
