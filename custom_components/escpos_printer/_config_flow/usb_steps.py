"""USB configuration steps mixin."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from ..capabilities import (
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    get_profile_choices_dict,
    suggest_profile,
)
from ..const import (
    CONF_CONNECTION_TYPE,
    CONF_IN_EP,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_USB,
    DEFAULT_IN_EP,
    DEFAULT_OUT_EP,
    DEFAULT_TIMEOUT,
)
from .usb_helpers import (
    _build_usb_device_choices,
    _can_connect_usb,
    _default_usb_choice_key,
    _discover_all_usb_devices,
    _discover_usb_printers,
    _generate_usb_unique_id,
    _parse_vid_pid,
    _usb_error_to_key,
)

if TYPE_CHECKING:
    from homeassistant.helpers.service_info.usb import UsbServiceInfo

_LOGGER = logging.getLogger(__name__)


async def _suggest_default_profile(
    hass: Any, devices: list[dict[str, Any]], profile_choices: dict[str, str]
) -> str:
    """Return a suggested profile for the first device's descriptor, or PROFILE_AUTO.

    A suggestion only preselects the dropdown default -- it never auto-commits.
    """
    if not devices:
        return PROFILE_AUTO
    first = devices[0]
    suggestion: str | None = await hass.async_add_executor_job(
        suggest_profile, first.get("product"), first.get("vendor_id"), first.get("product_id")
    )
    if suggestion and suggestion in profile_choices:
        return suggestion
    return PROFILE_AUTO


class UsbFlowMixin:
    """Mixin providing USB configuration steps.

    This mixin expects to be used with a class that has the following attributes
    and methods (typically provided by ConfigFlow and other mixins):
    - hass: HomeAssistant instance
    - _user_data: dict for storing flow data
    - _discovered_printers: list of discovered USB printers
    - _all_usb_devices: list of all USB devices
    - async_set_unique_id(): Set unique ID for the config entry
    - _abort_if_unique_id_configured(): Abort if ID already exists
    - async_show_form(): Show a form to the user
    - async_abort(): Abort the flow
    - async_step_codepage(): Handle codepage configuration step
    - async_step_custom_profile(): Handle custom profile step
    """

    # These attributes are expected from the main flow class
    hass: Any
    _user_data: dict[str, Any]
    _discovered_printers: list[dict[str, Any]]
    _all_usb_devices: list[dict[str, Any]]

    async def async_step_usb_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle USB printer selection/configuration.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Config flow USB step input: %s", user_input)

            # Handle special options
            selected_device = user_input.get("usb_device")
            if selected_device == "__manual__":
                return await self.async_step_usb_manual()
            if selected_device == "__browse_all__":
                return await self.async_step_usb_all_devices()

            # Find the exact printer by matching the choice key
            selected_printer = None
            for printer in self._discovered_printers:
                if printer.get("_choice_key") == selected_device:
                    selected_printer = printer
                    break

            if selected_printer is None:
                errors["base"] = "invalid_usb_device"
                vendor_id, product_id = 0, 0
                printer_name = ""
                serial_number = None
            else:
                vendor_id = selected_printer["vendor_id"]
                product_id = selected_printer["product_id"]
                printer_name = f"{selected_printer['manufacturer']} {selected_printer['product']}"
                serial_number = selected_printer.get("serial_number")

            if not errors:
                timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))

                # Always set a unique ID (falls back to vid:pid when the
                # device reports no serial) so serial-less printers -- most
                # cheap POS-58/80 hardware -- can't be added twice.
                unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
                self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

                _LOGGER.debug("Attempting USB connection test to %04X:%04X", vendor_id, product_id)
                ok, error_code, errno = await self.hass.async_add_executor_job(
                    _can_connect_usb, vendor_id, product_id, timeout
                )
                if ok:
                    _LOGGER.debug(
                        "USB connection test succeeded for %04X:%04X", vendor_id, product_id
                    )

                    profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                    self._user_data = {
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                        CONF_VENDOR_ID: vendor_id,
                        CONF_PRODUCT_ID: product_id,
                        CONF_IN_EP: user_input.get(CONF_IN_EP, DEFAULT_IN_EP),
                        CONF_OUT_EP: user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP),
                        CONF_TIMEOUT: timeout,
                        CONF_PROFILE: profile,
                        "_printer_name": printer_name,  # For entry title
                    }

                    # If custom profile selected, go to custom profile step
                    if profile == PROFILE_CUSTOM:
                        return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

                    return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

                _LOGGER.warning(
                    "USB connection test failed for %04X:%04X (errno=%s): %s",
                    vendor_id,
                    product_id,
                    errno,
                    error_code,
                )
                errors["base"] = _usb_error_to_key(error_code)

        # Discover USB printers
        self._discovered_printers = await self.hass.async_add_executor_job(_discover_usb_printers)

        # Build device choices - handles multiple devices with same VID/PID
        device_choices = _build_usb_device_choices(self._discovered_printers)

        if not self._discovered_printers:
            # No printers found, show manual entry message
            _LOGGER.info("No USB thermal printers discovered")

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        # Preselect a suggested profile for the default (first) device, as a
        # suggested_value rather than a schema default so clearing the field
        # sticks (the frontend omits cleared optional fields; a schema
        # default would reinstate the suggestion). An error redisplay keeps
        # the user's submitted choice instead.
        # ponytail: suggestion follows the first discovered printer only;
        # re-computing per selected device would need a two-step flow.
        suggested_profile = (
            user_input.get(CONF_PROFILE, PROFILE_AUTO)
            if user_input is not None
            else await _suggest_default_profile(
                self.hass, self._discovered_printers, profile_choices
            )
        )

        # _build_usb_device_choices always appends "__manual__", so
        # device_choices is never empty here.
        default_device = (
            next(iter(device_choices.keys())) if self._discovered_printers else "__browse_all__"
        )
        data_schema = self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
            vol.Schema(
                {
                    vol.Required("usb_device", default=default_device): vol.In(device_choices),
                    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                    vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
                }
            ),
            {CONF_PROFILE: suggested_profile},
        )

        return self.async_show_form(step_id="usb_select", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]

    async def async_step_usb_all_devices(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle selection from all USB devices (not just known printers).

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Config flow USB all devices step input: %s", user_input)

            # Handle manual entry option
            selected_device = user_input.get("usb_device")
            if selected_device == "__manual__":
                return await self.async_step_usb_manual()

            # Find the exact device by matching the choice key
            selected_usb_device = None
            for device in self._all_usb_devices:
                if device.get("_choice_key") == selected_device:
                    selected_usb_device = device
                    break

            # Parse endpoint settings up-front so the variables are
            # unconditionally defined before any later code path uses
            # them (CodeQL py/uninitialized-local-variable). The values
            # are only consumed inside the ``not errors`` branches below.
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
            in_ep = int(user_input.get(CONF_IN_EP, DEFAULT_IN_EP))
            out_ep = int(user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP))

            if selected_usb_device is None:
                errors["base"] = "invalid_usb_device"
                vendor_id, product_id = 0, 0
                device_name = ""
                serial_number = None
            else:
                vendor_id = selected_usb_device["vendor_id"]
                product_id = selected_usb_device["product_id"]
                device_name = (
                    f"{selected_usb_device['manufacturer']} {selected_usb_device['product']}"
                )
                serial_number = selected_usb_device.get("serial_number")

            # Validate endpoint addresses (0x00-0xFF)
            if not errors and (not (0x00 <= in_ep <= 0xFF) or not (0x00 <= out_ep <= 0xFF)):
                errors["base"] = "invalid_endpoint"

            if not errors:
                # Always set a unique ID (falls back to vid:pid when the
                # device reports no serial) so serial-less printers -- most
                # cheap POS-58/80 hardware -- can't be added twice.
                unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
                self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X (in_ep=%02X, out_ep=%02X)",
                    vendor_id,
                    product_id,
                    in_ep,
                    out_ep,
                )
                ok, error_code, errno = await self.hass.async_add_executor_job(
                    _can_connect_usb, vendor_id, product_id, timeout, in_ep, out_ep
                )
                if ok:
                    _LOGGER.debug(
                        "USB connection test succeeded for %04X:%04X", vendor_id, product_id
                    )

                    profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                    self._user_data = {
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                        CONF_VENDOR_ID: vendor_id,
                        CONF_PRODUCT_ID: product_id,
                        CONF_IN_EP: in_ep,
                        CONF_OUT_EP: out_ep,
                        CONF_TIMEOUT: timeout,
                        CONF_PROFILE: profile,
                        "_printer_name": device_name,  # For entry title
                    }

                    # If custom profile selected, go to custom profile step
                    if profile == PROFILE_CUSTOM:
                        return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

                    return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

                _LOGGER.warning(
                    "USB connection test failed for %04X:%04X (errno=%s): %s",
                    vendor_id,
                    product_id,
                    errno,
                    error_code,
                )
                errors["base"] = _usb_error_to_key(error_code)

        # Discover all USB devices
        self._all_usb_devices = await self.hass.async_add_executor_job(_discover_all_usb_devices)

        # Build device choices - no "Browse all" option since we're already showing all
        device_choices = _build_usb_device_choices(self._all_usb_devices, include_browse_all=False)

        if not self._all_usb_devices:
            # No devices found at all
            _LOGGER.info("No USB devices discovered")
            return await self.async_step_usb_manual()

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        # Preselect a suggested profile for the default (first) device, as a
        # suggested_value for the same clear-must-stick reason as usb_select.
        # ponytail: suggestion follows the first discovered device only;
        # re-computing per selected device would need a two-step flow.
        suggested_profile = (
            user_input.get(CONF_PROFILE, PROFILE_AUTO)
            if user_input is not None
            else await _suggest_default_profile(self.hass, self._all_usb_devices, profile_choices)
        )

        # Show form with all USB devices - include endpoint configuration
        default_device = next(iter(device_choices.keys()))
        data_schema = self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
            vol.Schema(
                {
                    vol.Required("usb_device", default=default_device): vol.In(device_choices),
                    vol.Optional(CONF_IN_EP, default=DEFAULT_IN_EP): int,
                    vol.Optional(CONF_OUT_EP, default=DEFAULT_OUT_EP): int,
                    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                    vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
                }
            ),
            {CONF_PROFILE: suggested_profile},
        )

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="usb_all_devices", data_schema=data_schema, errors=errors
        )

    async def async_step_usb_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual USB printer configuration.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            _LOGGER.debug("Config flow USB manual step input: %s", user_input)

            # Parse endpoint settings up-front so the variables are
            # unconditionally defined before any later code path uses
            # them (CodeQL py/uninitialized-local-variable). The values
            # are only consumed inside the ``not errors`` branches below.
            timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
            in_ep = int(user_input.get(CONF_IN_EP, DEFAULT_IN_EP))
            out_ep = int(user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP))

            try:
                vendor_id = _parse_vid_pid(user_input.get(CONF_VENDOR_ID, 0))
                product_id = _parse_vid_pid(user_input.get(CONF_PRODUCT_ID, 0))
                # VID/PID must be in range 0x0001-0xFFFF (1-65535)
                if not (0x0001 <= vendor_id <= 0xFFFF) or not (0x0001 <= product_id <= 0xFFFF):
                    errors["base"] = "invalid_usb_device"
            except ValueError, TypeError:
                errors["base"] = "invalid_usb_device"
                vendor_id, product_id = 0, 0

            # Validate endpoint addresses (0x00-0xFF)
            if not errors and (not (0x00 <= in_ep <= 0xFF) or not (0x00 <= out_ep <= 0xFF)):
                errors["base"] = "invalid_endpoint"

            if not errors:
                # A manual entry has no serial number, so the base id is
                # just vendor:product -- but manual entry legitimately
                # supports custom in_ep/out_ep for multi-interface
                # composite devices, so two same-VID:PID entries can be
                # real. Only fold the endpoints into the id when they
                # differ from the defaults, so the common case still
                # dedupes against the default-endpoint entry.
                unique_id = _generate_usb_unique_id(vendor_id, product_id, None)
                if in_ep != DEFAULT_IN_EP or out_ep != DEFAULT_OUT_EP:
                    unique_id = f"{unique_id}:{in_ep:02x}:{out_ep:02x}"
                await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
                self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X (in_ep=%02X, out_ep=%02X)",
                    vendor_id,
                    product_id,
                    in_ep,
                    out_ep,
                )
                ok, error_code, errno = await self.hass.async_add_executor_job(
                    _can_connect_usb, vendor_id, product_id, timeout, in_ep, out_ep
                )
                if ok:
                    _LOGGER.debug(
                        "USB connection test succeeded for %04X:%04X", vendor_id, product_id
                    )

                    profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
                    self._user_data = {
                        CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                        CONF_VENDOR_ID: vendor_id,
                        CONF_PRODUCT_ID: product_id,
                        CONF_IN_EP: in_ep,
                        CONF_OUT_EP: out_ep,
                        CONF_TIMEOUT: timeout,
                        CONF_PROFILE: profile,
                        "_printer_name": f"USB Printer {vendor_id:04X}:{product_id:04X}",
                    }

                    # If custom profile selected, go to custom profile step
                    if profile == PROFILE_CUSTOM:
                        return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

                    return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

                _LOGGER.warning(
                    "USB connection test failed for %04X:%04X (errno=%s): %s",
                    vendor_id,
                    product_id,
                    errno,
                    error_code,
                )
                errors["base"] = _usb_error_to_key(error_code)

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        data_schema = vol.Schema(
            {
                # str, not int -- voluptuous_serialize can't render a
                # custom coercion callable into a form field, and an
                # `int`-typed field rejects the "0x04B8" hex form the
                # help text recommends. Parsing happens in the handler
                # via _parse_vid_pid above.
                vol.Required(CONF_VENDOR_ID): str,
                vol.Required(CONF_PRODUCT_ID): str,
                vol.Optional(CONF_IN_EP, default=DEFAULT_IN_EP): int,
                vol.Optional(CONF_OUT_EP, default=DEFAULT_OUT_EP): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )

        return self.async_show_form(step_id="usb_manual", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]

    async def async_step_usb(self, discovery_info: UsbServiceInfo) -> ConfigFlowResult:
        """Handle USB discovery from Home Assistant.

        This method is called by HA when a USB device matching the manifest's
        usb section is detected.

        Args:
            discovery_info: UsbServiceInfo from HA USB discovery

        Returns:
            FlowResult containing the next step
        """
        _LOGGER.debug("USB discovery info: %s", discovery_info)

        # Extract VID/PID from discovery info
        try:
            vendor_id = int(discovery_info.vid, 16) if discovery_info.vid else 0
            product_id = int(discovery_info.pid, 16) if discovery_info.pid else 0
        except ValueError, TypeError:
            vendor_id, product_id = 0, 0

        if not vendor_id or not product_id:
            return self.async_abort(reason="invalid_discovery_info")  # type: ignore[attr-defined,no-any-return]

        # Set unique ID (includes serial if available to distinguish identical printers)
        serial_number = discovery_info.serial_number
        unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
        await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
        self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

        # Store discovery info
        self._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_VENDOR_ID: vendor_id,
            CONF_PRODUCT_ID: product_id,
            CONF_IN_EP: DEFAULT_IN_EP,
            CONF_OUT_EP: DEFAULT_OUT_EP,
            CONF_TIMEOUT: DEFAULT_TIMEOUT,
            "_printer_name": discovery_info.description
            or f"USB Printer {vendor_id:04X}:{product_id:04X}",
        }

        # Show confirmation step
        return await self.async_step_usb_confirm()

    async def async_step_usb_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm USB printer discovered by Home Assistant.

        Args:
            user_input: User confirmation

        Returns:
            FlowResult containing the next step
        """
        if user_input is not None:
            # User confirmed, proceed to codepage configuration
            profile = user_input.get(CONF_PROFILE, PROFILE_AUTO)
            self._user_data[CONF_PROFILE] = profile

            if profile == PROFILE_CUSTOM:
                return await self.async_step_custom_profile()  # type: ignore[attr-defined,no-any-return]

            return await self.async_step_codepage()  # type: ignore[attr-defined,no-any-return]

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        printer_name = self._user_data.get("_printer_name", "USB Printer")

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="usb_confirm",
            data_schema=data_schema,
            description_placeholders={"printer_name": printer_name},
        )

    async def async_step_reconfigure_usb(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle reconfiguration of an existing USB printer entry.

        vendor_id:product_id[:serial] is the printer's hardware identity
        (see :func:`_generate_usb_unique_id`), so re-picking a *different*
        device is treated as pointing this entry at a different physical
        printer and aborts via the standard reconfigure unique-ID
        mismatch guard.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_device = user_input.get("usb_device")
            if selected_device == "__manual__":
                return await self.async_step_reconfigure_usb_manual()

            selected_printer = next(
                (p for p in self._discovered_printers if p.get("_choice_key") == selected_device),
                None,
            )
            if selected_printer is None:
                errors["base"] = "invalid_usb_device"
            else:
                result = await self._finalize_usb_reconfigure(
                    vendor_id=selected_printer["vendor_id"],
                    product_id=selected_printer["product_id"],
                    serial_number=selected_printer.get("serial_number"),
                    timeout=float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
                    errors=errors,
                )
                if result is not None:
                    return result

        self._discovered_printers = await self.hass.async_add_executor_job(_discover_usb_printers)
        device_choices = _build_usb_device_choices(
            self._discovered_printers, include_browse_all=False
        )
        reconfigure_entry = self._get_reconfigure_entry()  # type: ignore[attr-defined]
        # reconfigure_entry.data has no "usb_device" key (that's a UI-only
        # choice-dict key, never stored) -- match on the entry's stored
        # vendor/product ID so the dropdown preselects the configured
        # device. Falls back to the first discovered device when the
        # configured one isn't present (e.g. unplugged).
        default_device = _default_usb_choice_key(
            self._discovered_printers, reconfigure_entry.data
        ) or next(iter(device_choices.keys()))
        data_schema = vol.Schema(
            {
                vol.Required("usb_device", default=default_device): vol.In(device_choices),
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
            }
        )
        suggested_values: dict[str, Any] = dict(user_input or reconfigure_entry.data)
        suggested_values.setdefault("usb_device", default_device)
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="reconfigure_usb",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                data_schema, suggested_values
            ),
            errors=errors,
        )

    async def async_step_reconfigure_usb_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual VID:PID fallback for USB reconfigure when discovery finds nothing."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                vendor_id = _parse_vid_pid(user_input.get(CONF_VENDOR_ID, 0))
                product_id = _parse_vid_pid(user_input.get(CONF_PRODUCT_ID, 0))
                if not (0x0001 <= vendor_id <= 0xFFFF) or not (0x0001 <= product_id <= 0xFFFF):
                    errors["base"] = "invalid_usb_device"
            except ValueError, TypeError:
                errors["base"] = "invalid_usb_device"
                vendor_id, product_id = 0, 0

            if not errors:
                result = await self._finalize_usb_reconfigure(
                    vendor_id=vendor_id,
                    product_id=product_id,
                    serial_number=None,
                    timeout=float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)),
                    errors=errors,
                )
                if result is not None:
                    return result

        data_schema = vol.Schema(
            {
                # str, not int -- see async_step_usb_manual for why.
                vol.Required(CONF_VENDOR_ID): str,
                vol.Required(CONF_PRODUCT_ID): str,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
            }
        )
        reconfigure_entry = self._get_reconfigure_entry()  # type: ignore[attr-defined]
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="reconfigure_usb_manual",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                data_schema, user_input or reconfigure_entry.data
            ),
            errors=errors,
        )

    async def _finalize_usb_reconfigure(
        self,
        *,
        vendor_id: int,
        product_id: int,
        serial_number: str | None,
        timeout: float,
        errors: dict[str, str],
    ) -> ConfigFlowResult | None:
        """Set unique ID, guard identity, probe, and finish the reconfigure flow.

        Returns a ``ConfigFlowResult`` on success (caller returns it
        directly). On failure, mutates ``errors["base"]`` and returns
        ``None`` so the caller re-renders its own form with the error.
        """
        reconfigure_entry = self._get_reconfigure_entry()  # type: ignore[attr-defined]
        unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
        existing_unique_id = reconfigure_entry.unique_id
        # The reconfigure forms only collect vendor_id/product_id --
        # reconfigure_usb_manual never asks for a serial, and
        # reconfigure_usb can't reproduce a manual entry's custom-endpoint
        # suffix -- so a freshly computed id legitimately drops a suffix
        # the original entry had. Compare on the "usb:vid:pid" base only:
        # a match there means it's still the same physical device, so
        # keep the existing unique_id instead of mismatching on a suffix
        # the form can't know. A genuinely different vid:pid still falls
        # through to the mismatch guard below.
        if (
            existing_unique_id is not None
            and unique_id.split(":")[:3] == existing_unique_id.split(":")[:3]
        ):
            unique_id = existing_unique_id
        await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
        # Pre-existing serial-less entries created before unique IDs were
        # backfilled (or via the manual-entry step, which historically set
        # none) have unique_id=None -- that never matches a freshly
        # computed id, so the mismatch guard would permanently block
        # reconfigure. Skip it once and let this reconfigure adopt/set the
        # unique ID instead -- but still guard against the id landing on a
        # *different* already-configured entry (the mismatch guard can't
        # catch this case since it only fires when there's an original id
        # to compare against).
        if existing_unique_id is not None:
            self._abort_if_unique_id_mismatch()  # type: ignore[attr-defined]
        else:
            colliding = self.hass.config_entries.async_entry_for_domain_unique_id(
                self.handler,  # type: ignore[attr-defined]
                unique_id,
            )
            if colliding is not None and colliding.entry_id != reconfigure_entry.entry_id:
                return self.async_abort(reason="already_configured")  # type: ignore[attr-defined,no-any-return]

        in_ep = reconfigure_entry.data.get(CONF_IN_EP, DEFAULT_IN_EP)
        out_ep = reconfigure_entry.data.get(CONF_OUT_EP, DEFAULT_OUT_EP)
        ok, error_code, errno = await self.hass.async_add_executor_job(
            _can_connect_usb, vendor_id, product_id, timeout, in_ep, out_ep
        )
        if ok:
            return self.async_update_reload_and_abort(  # type: ignore[attr-defined,no-any-return]
                reconfigure_entry,
                unique_id=unique_id,
                data_updates={
                    CONF_VENDOR_ID: vendor_id,
                    CONF_PRODUCT_ID: product_id,
                    CONF_TIMEOUT: timeout,
                },
            )
        _LOGGER.warning(
            "USB reconfigure connection test failed for %04X:%04X (errno=%s): %s",
            vendor_id,
            product_id,
            errno,
            error_code,
        )
        errors["base"] = _usb_error_to_key(error_code)
        return None
