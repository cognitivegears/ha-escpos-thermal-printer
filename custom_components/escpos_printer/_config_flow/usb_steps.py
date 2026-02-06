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
    _discover_all_usb_devices,
    _discover_usb_printers,
    _generate_usb_unique_id,
    _usb_error_to_key,
)

if TYPE_CHECKING:
    from homeassistant.components.usb import UsbServiceInfo

_LOGGER = logging.getLogger(__name__)


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

    async def async_step_usb_select(  # noqa: PLR0912
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

                # Only set unique ID if we have a serial number to distinguish devices
                if serial_number:
                    unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                    await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
                    self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X", vendor_id, product_id
                )
                ok, error_code, errno = await self.hass.async_add_executor_job(
                    _can_connect_usb, vendor_id, product_id, timeout
                )
                if ok:
                    _LOGGER.debug("USB connection test succeeded for %04X:%04X", vendor_id, product_id)

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

        # Build schema based on whether printers were found
        if device_choices:
            default_device = next(iter(device_choices.keys())) if self._discovered_printers else "__browse_all__"
            data_schema = vol.Schema(
                {
                    vol.Required("usb_device", default=default_device): vol.In(device_choices),
                    vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                    vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
                }
            )
        else:
            # Redirect to manual entry if no devices found
            return await self.async_step_usb_manual()

        return self.async_show_form(step_id="usb_select", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]

    async def async_step_usb_all_devices(  # noqa: PLR0912
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

            if selected_usb_device is None:
                errors["base"] = "invalid_usb_device"
                vendor_id, product_id = 0, 0
                device_name = ""
                serial_number = None
            else:
                vendor_id = selected_usb_device["vendor_id"]
                product_id = selected_usb_device["product_id"]
                device_name = f"{selected_usb_device['manufacturer']} {selected_usb_device['product']}"
                serial_number = selected_usb_device.get("serial_number")

            if not errors:
                timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
                in_ep = int(user_input.get(CONF_IN_EP, DEFAULT_IN_EP))
                out_ep = int(user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP))

                # Validate endpoint addresses (0x00-0xFF)
                if not (0x00 <= in_ep <= 0xFF) or not (0x00 <= out_ep <= 0xFF):
                    errors["base"] = "invalid_endpoint"

            if not errors:
                # Only set unique ID if we have a serial number to distinguish devices
                if serial_number:
                    unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                    await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
                    self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X (in_ep=%02X, out_ep=%02X)",
                    vendor_id, product_id, in_ep, out_ep
                )
                ok, error_code, errno = await self.hass.async_add_executor_job(
                    _can_connect_usb, vendor_id, product_id, timeout, in_ep, out_ep
                )
                if ok:
                    _LOGGER.debug("USB connection test succeeded for %04X:%04X", vendor_id, product_id)

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

        # Show form with all USB devices - include endpoint configuration
        default_device = next(iter(device_choices.keys()))
        data_schema = vol.Schema(
            {
                vol.Required("usb_device", default=default_device): vol.In(device_choices),
                vol.Optional(CONF_IN_EP, default=DEFAULT_IN_EP): int,
                vol.Optional(CONF_OUT_EP, default=DEFAULT_OUT_EP): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )

        return self.async_show_form(step_id="usb_all_devices", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]

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

            try:
                vendor_id = int(user_input.get(CONF_VENDOR_ID, 0))
                product_id = int(user_input.get(CONF_PRODUCT_ID, 0))
                # VID/PID must be in range 0x0001-0xFFFF (1-65535)
                if not (0x0001 <= vendor_id <= 0xFFFF) or not (0x0001 <= product_id <= 0xFFFF):
                    errors["base"] = "invalid_usb_device"
            except (ValueError, TypeError):
                errors["base"] = "invalid_usb_device"
                vendor_id, product_id = 0, 0

            if not errors:
                timeout = float(user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT))
                in_ep = int(user_input.get(CONF_IN_EP, DEFAULT_IN_EP))
                out_ep = int(user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP))

                # Validate endpoint addresses (0x00-0xFF)
                if not (0x00 <= in_ep <= 0xFF) or not (0x00 <= out_ep <= 0xFF):
                    errors["base"] = "invalid_endpoint"

            if not errors:
                # Note: No unique_id set for manual entry - allows multiple identical printers

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X (in_ep=%02X, out_ep=%02X)",
                    vendor_id, product_id, in_ep, out_ep
                )
                ok, error_code, errno = await self.hass.async_add_executor_job(
                    _can_connect_usb, vendor_id, product_id, timeout, in_ep, out_ep
                )
                if ok:
                    _LOGGER.debug("USB connection test succeeded for %04X:%04X", vendor_id, product_id)

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
                vol.Required(CONF_VENDOR_ID): int,
                vol.Required(CONF_PRODUCT_ID): int,
                vol.Optional(CONF_IN_EP, default=DEFAULT_IN_EP): int,
                vol.Optional(CONF_OUT_EP, default=DEFAULT_OUT_EP): int,
                vol.Optional(CONF_TIMEOUT, default=DEFAULT_TIMEOUT): vol.Coerce(float),
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )

        return self.async_show_form(step_id="usb_manual", data_schema=data_schema, errors=errors)  # type: ignore[attr-defined,no-any-return]

    async def async_step_usb(
        self, discovery_info: UsbServiceInfo
    ) -> ConfigFlowResult:
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
        except (ValueError, TypeError):
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
            "_printer_name": discovery_info.description or f"USB Printer {vendor_id:04X}:{product_id:04X}",
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
