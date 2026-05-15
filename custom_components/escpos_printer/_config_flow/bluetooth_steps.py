"""Bluetooth Classic / RFCOMM configuration steps mixin."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.exceptions import HomeAssistantError
import voluptuous as vol

from ..capabilities import (
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    get_profile_choices_dict,
)
from ..const import (
    BT_MANUAL_ENTRY_KEY,
    BT_SHOW_ALL_KEY,
    CONF_BT_DEVICE,
    CONF_BT_MAC,
    CONF_CONNECTION_TYPE,
    CONF_PROFILE,
    CONF_RFCOMM_CHANNEL,
    CONF_TIMEOUT,
    CONNECTION_TYPE_BLUETOOTH,
    DEFAULT_RFCOMM_CHANNEL,
    DEFAULT_TIMEOUT,
)
from ..security import sanitize_log_message, validate_rfcomm_channel
from .bluetooth_helpers import (
    _bt_error_to_key,
    _build_bt_device_choices,
    _can_connect_bluetooth,
    _generate_bt_unique_id,
    _list_paired_bluetooth_devices,
    _normalize_bt_mac,
)

_LOGGER = logging.getLogger(__name__)


class BluetoothFlowMixin:
    """Mixin providing Bluetooth Classic / RFCOMM configuration steps.

    This mixin expects to be used with a class that has the following attributes
    and methods (typically provided by ConfigFlow and other mixins):
    - hass: HomeAssistant instance
    - show_advanced_options: bool — HA's "advanced settings" toggle
    - _user_data: dict for storing flow data
    - _paired_bt_devices: list of paired Bluetooth devices
    - _show_all_bt_devices: bool — when True, drop the imaging-only filter
    - _pending_bt: in-progress BT config awaiting channel-retry
    - async_set_unique_id(): Set unique ID for the config entry
    - _abort_if_unique_id_configured(): Abort if ID already exists
    - async_show_form(): Show a form to the user
    - async_step_codepage(): Handle codepage configuration step
    - async_step_custom_profile(): Handle custom profile step
    """

    hass: Any
    show_advanced_options: bool
    _user_data: dict[str, Any]
    _paired_bt_devices: list[dict[str, Any]]
    _show_all_bt_devices: bool
    _pending_bt: dict[str, Any]

    async def async_step_bluetooth_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle Bluetooth printer selection from paired devices."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(
                "Config flow Bluetooth select input keys: %s",
                sorted(user_input.keys()),
            )
            selected = user_input.get(CONF_BT_DEVICE)
            if selected == BT_MANUAL_ENTRY_KEY:
                return await self.async_step_bluetooth_manual()
            if selected == BT_SHOW_ALL_KEY:
                self._show_all_bt_devices = True
                return await self.async_step_bluetooth_select()

            chosen = next(
                (d for d in self._paired_bt_devices if d.get("_choice_key") == selected),
                None,
            )
            if chosen is None:
                errors["base"] = "invalid_bt_mac"
            else:
                mac = chosen["mac"]
                timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
                try:
                    channel = validate_rfcomm_channel(
                        user_input.get(CONF_RFCOMM_CHANNEL, DEFAULT_RFCOMM_CHANNEL)
                    )
                except HomeAssistantError:
                    errors["base"] = "invalid_rfcomm_channel"
                    channel = DEFAULT_RFCOMM_CHANNEL
                profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)

            if not errors:
                assert chosen is not None  # narrowed by errors check above
                result = await self._finalize_bt_step(
                    mac=mac,
                    channel=channel,
                    timeout=timeout,
                    profile=profile,
                    printer_name=chosen.get("name") or f"Bluetooth Printer {mac}",
                    errors=errors,
                    return_step="bluetooth_select",
                )
                if result is not None:
                    return result

        # Discover paired devices via bluez D-Bus, but only on the first render.
        # Re-renders after a validation/connection error reuse the cached list -
        # the bluez tree walk is 50-200KB on dense BT hosts, no need to redo it
        # while the user retries.
        if not self._paired_bt_devices:
            self._paired_bt_devices = await _list_paired_bluetooth_devices()
        if not self._paired_bt_devices:
            return await self.async_step_bluetooth_no_devices()

        # Filter to imaging-class devices unless the user explicitly opted to
        # see everything. If the imaging filter would yield zero entries we
        # transparently disable it — handles printers that don't advertise the
        # class correctly (most cheap ESC/POS hardware doesn't).
        imaging_only = not self._show_all_bt_devices
        if imaging_only and not any(
            d.get("is_imaging") for d in self._paired_bt_devices
        ):
            imaging_only = False
        device_choices = _build_bt_device_choices(
            self._paired_bt_devices, imaging_only=imaging_only
        )
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)
        default_device = next(iter(device_choices.keys()))

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_BT_DEVICE, default=default_device): vol.In(device_choices),
            vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
            vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
        }
        # Channel is hidden by default — almost every ESC/POS printer uses 1.
        # Surface it only when "Advanced settings" is on in the user's HA
        # profile, OR when a previous attempt was refused at the default
        # channel. Otherwise we route to bluetooth_channel_retry on
        # `bt_channel_refused` to ask for a channel specifically.
        if self.show_advanced_options:
            schema_dict[
                vol.Optional(CONF_RFCOMM_CHANNEL, default=DEFAULT_RFCOMM_CHANNEL)
            ] = int
        data_schema = vol.Schema(schema_dict)
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="bluetooth_select", data_schema=data_schema, errors=errors
        )

    async def async_step_bluetooth_no_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Guidance step when no paired Bluetooth devices are visible.

        Shown when bluez D-Bus is unreachable (rootless Docker, missing
        ``/run/dbus`` mount, non-Linux) or when the host has no paired BT
        devices at all. Tells the user how to pair, then offers a path to
        manual MAC entry for users who already know the address.
        """
        if user_input is not None:
            return await self.async_step_bluetooth_manual()

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="bluetooth_no_devices",
            data_schema=vol.Schema({}),
            description_placeholders={
                "docs_url": (
                    "https://github.com/cognitivegears/ha-escpos-thermal-printer"
                    "#bluetooth-rfcomm-printers"
                )
            },
        )

    async def async_step_bluetooth_channel_retry(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a non-default RFCOMM channel after a 'channel refused' failure.

        Reached when the initial connect attempt returned ``bt_channel_refused``.
        The user has already picked a device; we just need a different channel
        than 1 (rare for ESC/POS, but some imaging printers use 2 or 3).
        """
        errors: dict[str, str] = {}
        pending = getattr(self, "_pending_bt", None) or {}

        if user_input is not None:
            try:
                channel = validate_rfcomm_channel(
                    user_input.get(CONF_RFCOMM_CHANNEL, DEFAULT_RFCOMM_CHANNEL)
                )
            except HomeAssistantError:
                errors["base"] = "invalid_rfcomm_channel"
                channel = DEFAULT_RFCOMM_CHANNEL

            if not errors:
                result = await self._finalize_bt_step(
                    mac=pending["mac"],
                    channel=channel,
                    timeout=pending["timeout"],
                    profile=pending["profile"],
                    printer_name=pending["printer_name"],
                    errors=errors,
                    return_step="bluetooth_channel_retry",
                )
                if result is not None:
                    return result

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="bluetooth_channel_retry",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_RFCOMM_CHANNEL, default=pending.get("channel", 2)
                    ): int,
                }
            ),
            errors=errors,
            description_placeholders={
                "mac": sanitize_log_message(pending.get("mac", "")),
            },
        )

    async def async_step_bluetooth_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual Bluetooth MAC entry."""
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug(
                "Config flow Bluetooth manual input keys: %s",
                sorted(user_input.keys()),
            )
            raw_mac = str(user_input.get(CONF_BT_MAC, "")).strip()
            mac = _normalize_bt_mac(raw_mac)
            if mac is None:
                errors["base"] = "invalid_bt_mac"

            try:
                channel = validate_rfcomm_channel(
                    user_input.get(CONF_RFCOMM_CHANNEL, DEFAULT_RFCOMM_CHANNEL)
                )
            except HomeAssistantError:
                errors["base"] = "invalid_rfcomm_channel"
                channel = DEFAULT_RFCOMM_CHANNEL

            if not errors:
                assert mac is not None  # narrowed by errors check
                timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
                profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                result = await self._finalize_bt_step(
                    mac=mac,
                    channel=channel,
                    timeout=timeout,
                    profile=profile,
                    printer_name=f"Bluetooth Printer {mac}",
                    errors=errors,
                    return_step="bluetooth_manual",
                )
                if result is not None:
                    return result

        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)
        # Manual entry keeps the channel field visible — power users typing in
        # a MAC are likely the ones who'd also tweak the channel — but defaults
        # remain at 1.
        data_schema = vol.Schema(
            {
                vol.Required(CONF_BT_MAC): str,
                vol.Optional(CONF_RFCOMM_CHANNEL, default=DEFAULT_RFCOMM_CHANNEL): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="bluetooth_manual", data_schema=data_schema, errors=errors
        )

    async def _finalize_bt_step(
        self,
        *,
        mac: str,
        channel: int,
        timeout: float,
        profile: str,
        printer_name: str,
        errors: dict[str, str],
        return_step: str,
    ) -> ConfigFlowResult | None:
        """Set unique ID, run the connect probe, branch to next step.

        Returns a ConfigFlowResult on success (caller returns it directly).
        On failure, mutates ``errors["base"]`` and returns ``None`` so the
        caller can re-render its own form with the error. Special-cases
        ``bt_channel_refused`` by routing to the channel-retry step instead
        of merely blaming the form.
        """
        await self.async_set_unique_id(_generate_bt_unique_id(mac))  # type: ignore[attr-defined]
        self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

        _LOGGER.debug(
            "Attempting Bluetooth connection test to %s ch=%s",
            sanitize_log_message(mac),
            channel,
        )
        ok, error_code, err_no = await self.hass.async_add_executor_job(
            _can_connect_bluetooth, mac, channel, timeout
        )
        if ok:
            self._user_data = {
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
                CONF_BT_MAC: mac,
                CONF_RFCOMM_CHANNEL: channel,
                CONF_TIMEOUT: timeout,
                CONF_PROFILE: profile,
                "_printer_name": printer_name,
            }
            if profile == PROFILE_CUSTOM:
                return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]
            return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

        _LOGGER.warning(
            "Bluetooth connection test failed for %s ch=%s (errno=%s): %s",
            sanitize_log_message(mac),
            channel,
            err_no,
            error_code,
        )
        # Special-case: channel was refused by the printer. Don't make the user
        # re-pick the device — route to a focused step that asks for the
        # channel and re-runs the probe.
        if error_code == "channel_refused" and return_step != "bluetooth_channel_retry":
            self._pending_bt = {
                "mac": mac,
                "channel": channel,
                "timeout": timeout,
                "profile": profile,
                "printer_name": printer_name,
            }
            return await self.async_step_bluetooth_channel_retry()
        errors["base"] = _bt_error_to_key(error_code)
        return None
