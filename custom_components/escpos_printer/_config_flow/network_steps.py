"""Network configuration steps mixin."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.typing import UNDEFINED, UndefinedType
import voluptuous as vol

from ..capabilities import (
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    get_profile_choices_dict,
)
from ..capabilities.suggestions import suggest_profile
from ..const import (
    CONF_CONNECTION_TYPE,
    CONF_DETECTED_MANUFACTURER,
    CONF_DETECTED_MODEL,
    CONF_MAC_ADDRESS,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONNECTION_TYPE_NETWORK,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
)
from .network_helpers import (
    _can_connect,
    is_auto_network_title,
    make_network_entry_title,
    query_printer_id,
)

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
    _detected: dict[str, str]
    _discovery_host: str | None
    _discovery_port: int | None
    _discovery_mac: str | None

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
            host = str(user_input[CONF_HOST]).strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

            # Normalise the unique_id so "Printer.local" / "printer.local"
            # (hostnames are case-insensitive) don't create duplicate
            # entries for the same printer. IP literals are unaffected by
            # lowercasing.
            await self.async_set_unique_id(f"{host.lower()}:{port}")  # type: ignore[attr-defined]
            self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

            _LOGGER.debug("Attempting connection test to %s:%s (timeout=%s)", host, port, timeout)
            ok = bool(host) and await self.hass.async_add_executor_job(
                _can_connect, host, port, timeout
            )
            if ok:
                _LOGGER.debug("Connection test succeeded for %s:%s", host, port)

                # Discovery-time state (GS I result, MAC) only describes the
                # probed target -- the host field is just a suggested value,
                # and if the user points it at a different printer (or a
                # different port on the same host) that state must not be
                # attributed to it. DHCP always probes DEFAULT_PORT, so an
                # edited port alone is enough to misattribute identity.
                matches_discovery_target = (
                    host == self._discovery_host and port == self._discovery_port
                )
                detected = (
                    self._detected
                    if self._detected and matches_discovery_target
                    else (
                        await self.hass.async_add_executor_job(
                            query_printer_id, host, port, timeout
                        )
                        or {}
                    )
                )

                # Store data and determine next step
                profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                self._user_data = {
                    CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_TIMEOUT: timeout,
                    CONF_PROFILE: profile,
                }
                if detected.get("manufacturer"):
                    self._user_data[CONF_DETECTED_MANUFACTURER] = detected["manufacturer"]
                if detected.get("model"):
                    self._user_data[CONF_DETECTED_MODEL] = detected["model"]
                if self._discovery_mac and matches_discovery_target:
                    self._user_data[CONF_MAC_ADDRESS] = self._discovery_mac

                # If custom profile selected, go to custom profile step
                if profile == PROFILE_CUSTOM:
                    return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

                # Otherwise go to codepage step
                return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

            _LOGGER.warning("Connection test failed for %s:%s", host, port)
            errors["base"] = "cannot_connect"

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        # Discovery flows ran the GS I query before this form is shown, so
        # the detected model can preselect the profile dropdown (preselect
        # only -- the user always confirms). Manual flows query on submit.
        # The suggestion is a suggested_value, NOT a schema default: the
        # frontend omits a cleared optional field, and a schema default
        # would silently reinstate the suggestion the user just removed.
        # On an error redisplay the user's submitted choice (including a
        # cleared field) wins over the discovery suggestion.
        suggested_profile = PROFILE_AUTO
        if user_input is not None:
            suggested_profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
        elif self._discovery_host and self._detected.get("model"):
            suggestion = await self.hass.async_add_executor_job(
                suggest_profile, self._detected["model"], None, None
            )
            if suggestion and suggestion in profile_choices:
                suggested_profile = suggestion

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )
        # Prefer the host the user just typed (on error redisplay) over the
        # original discovery suggestion, so a typo fix isn't clobbered back
        # to the discovered address. This also preserves a manually typed
        # host across an error redisplay on non-discovery flows.
        suggested_values: dict[str, Any] = {}
        suggested_host = (user_input or {}).get(CONF_HOST) or self._discovery_host
        if suggested_host:
            suggested_values[CONF_HOST] = suggested_host
        if suggested_profile != PROFILE_AUTO:
            suggested_values[CONF_PROFILE] = suggested_profile
        if suggested_values:
            data_schema = self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                data_schema, suggested_values
            )

        return self.async_show_form(step_id="network", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]

    async def async_step_reconfigure_network(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing network printer entry.

        host:port *is* the unique_id for network printers, so changing
        either one legitimately changes the unique_id -- this mirrors HA
        core's address-based reconfigure pattern (e.g. ``cert_expiry``):
        update the unique_id directly instead of guarding it, and only
        abort if the new host/port collides with a *different* existing
        entry.
        """
        reconfigure_entry = self._get_reconfigure_entry()  # type: ignore[attr-defined]
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = user_input.get(CONF_PORT, DEFAULT_PORT)
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

            # ``_async_abort_entries_match`` does a raw, case-sensitive
            # compare against stored entry data, but the unique_id is
            # lower-cased -- "Printer.local" and "printer.local" would
            # pass that check yet collide on unique_id, leaving two
            # entries that share one id. Look up by the would-be
            # normalised unique_id instead, excluding this entry itself.
            new_unique_id = f"{host.lower()}:{port}"
            colliding = self.hass.config_entries.async_entry_for_domain_unique_id(
                self.handler,  # type: ignore[attr-defined]
                new_unique_id,
            )
            if colliding is not None and colliding.entry_id != reconfigure_entry.entry_id:
                return self.async_abort(reason="already_configured")  # type: ignore[attr-defined,no-any-return]

            ok = bool(host) and await self.hass.async_add_executor_job(
                _can_connect, host, port, timeout
            )
            if ok:
                detected = (
                    await self.hass.async_add_executor_job(query_printer_id, host, port, timeout)
                    or {}
                )

                # A fresh GS I query result REPLACES prior detected state
                # (present -> overwrite, absent -> key removed) since
                # reconfigure may point the entry at a different printer.
                # data_updates can only add/override keys, never delete
                # them, so build the full replacement dict instead. But
                # only clear the existing keys when the query actually
                # answered or the address changed -- reconfiguring just the
                # timeout while the printer is transiently busy (query
                # returns None) must not silently destroy a good prior
                # detection for the SAME address.
                addr_changed = (host.lower(), port) != (
                    str(reconfigure_entry.data.get(CONF_HOST, "")).lower(),
                    reconfigure_entry.data.get(CONF_PORT, DEFAULT_PORT),
                )
                new_data = {
                    **reconfigure_entry.data,
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_TIMEOUT: timeout,
                }
                if detected or addr_changed:
                    new_data.pop(CONF_DETECTED_MANUFACTURER, None)
                    new_data.pop(CONF_DETECTED_MODEL, None)
                    if detected.get("manufacturer"):
                        new_data[CONF_DETECTED_MANUFACTURER] = detected["manufacturer"]
                    if detected.get("model"):
                        new_data[CONF_DETECTED_MODEL] = detected["model"]
                # The stored MAC describes the address binding, not the GS I
                # reply -- it clears only when the address itself changes
                # (an edit may repoint the entry at different hardware the
                # MAC no longer describes), never on a transient query miss.
                if addr_changed:
                    new_data.pop(CONF_MAC_ADDRESS, None)

                # Only regenerate the title when the entry still carries an
                # auto-generated one -- a user's manual rename must never be
                # clobbered. Built from new_data so a fresh detection (or a
                # cleared one) is reflected in the new title.
                title: str | UndefinedType = UNDEFINED
                if is_auto_network_title(reconfigure_entry.title, reconfigure_entry.data):
                    title = make_network_entry_title(new_data)

                return self.async_update_reload_and_abort(  # type: ignore[attr-defined,no-any-return]
                    reconfigure_entry,
                    unique_id=new_unique_id,
                    title=title,
                    data=new_data,
                )
            errors["base"] = "cannot_connect"

        data_schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="reconfigure_network",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                data_schema, user_input or reconfigure_entry.data
            ),
            errors=errors,
        )
