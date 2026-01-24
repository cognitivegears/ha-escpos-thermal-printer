"""Main config flow for ESC/POS Thermal Printer integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
import voluptuous as vol

if TYPE_CHECKING:
    from homeassistant.components.usb import UsbServiceInfo

from ..capabilities import (
    OPTION_CUSTOM,
    PROFILE_AUTO,
    PROFILE_CUSTOM,
    get_profile_choices_dict,
    get_profile_codepages,
    get_profile_cut_modes,
    get_profile_line_widths,
    is_valid_codepage_for_profile,
    is_valid_profile,
)
from ..const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_IN_EP,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_IN_EP,
    DEFAULT_LINE_WIDTH,
    DEFAULT_OUT_EP,
    DEFAULT_PORT,
    DEFAULT_TIMEOUT,
    DOMAIN,
)
from .network_helpers import _can_connect
from .usb_helpers import (
    _build_usb_device_choices,
    _can_connect_usb,
    _discover_all_usb_devices,
    _discover_usb_printers,
    _generate_usb_unique_id,
    _parse_vid_pid,
    _usb_error_to_key,
)

_LOGGER = logging.getLogger(__name__)


class EscposConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for ESC/POS Thermal Printer."""

    VERSION = 3

    def __init__(self) -> None:
        """Initialize config flow."""
        self._user_data: dict[str, Any] = {}
        self._discovered_printers: list[dict[str, Any]] = []
        self._all_usb_devices: list[dict[str, Any]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 1: Connection type selection.

        Args:
            user_input: User provided configuration data

        Returns:
            FlowResult containing the next step or final result
        """
        if user_input is not None:
            connection_type = user_input.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
            self._user_data[CONF_CONNECTION_TYPE] = connection_type

            if connection_type == CONNECTION_TYPE_USB:
                return await self.async_step_usb_select()
            return await self.async_step_network()

        data_schema = vol.Schema(
            {
                vol.Required(CONF_CONNECTION_TYPE, default=CONNECTION_TYPE_NETWORK): vol.In(
                    {
                        CONNECTION_TYPE_NETWORK: "Network (TCP/IP)",
                        CONNECTION_TYPE_USB: "USB (Direct)",
                    }
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=data_schema)

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

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

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
                    return await self.async_step_custom_profile()

                # Otherwise go to codepage step
                return await self.async_step_codepage()

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

        return self.async_show_form(step_id="network", data_schema=data_schema, errors=errors)

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
                # Without serial, allow duplicates (like manual entry) since we can't
                # reliably identify which physical device is which
                if serial_number:
                    unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X", vendor_id, product_id
                )
                ok, error_code = await self.hass.async_add_executor_job(
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
                        return await self.async_step_custom_profile()

                    return await self.async_step_codepage()

                _LOGGER.warning("USB connection test failed for %04X:%04X: %s", vendor_id, product_id, error_code)
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

        return self.async_show_form(step_id="usb_select", data_schema=data_schema, errors=errors)

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
                    await self.async_set_unique_id(unique_id)
                    self._abort_if_unique_id_configured()

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X (in_ep=%02X, out_ep=%02X)",
                    vendor_id, product_id, in_ep, out_ep
                )
                ok, error_code = await self.hass.async_add_executor_job(
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
                        return await self.async_step_custom_profile()

                    return await self.async_step_codepage()

                _LOGGER.warning("USB connection test failed for %04X:%04X: %s", vendor_id, product_id, error_code)
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
        # since these may not be standard thermal printers
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

        return self.async_show_form(step_id="usb_all_devices", data_schema=data_schema, errors=errors)

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
                # since we don't have serial number info to distinguish them

                _LOGGER.debug(
                    "Attempting USB connection test to %04X:%04X (in_ep=%02X, out_ep=%02X)",
                    vendor_id, product_id, in_ep, out_ep
                )
                ok, error_code = await self.hass.async_add_executor_job(
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
                        return await self.async_step_custom_profile()

                    return await self.async_step_codepage()

                _LOGGER.warning("USB connection test failed for %04X:%04X: %s", vendor_id, product_id, error_code)
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

        return self.async_show_form(step_id="usb_manual", data_schema=data_schema, errors=errors)

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
        # HA provides these as hex strings (e.g., "04B8") in UsbServiceInfo
        try:
            vendor_id = int(discovery_info.vid, 16) if discovery_info.vid else 0
            product_id = int(discovery_info.pid, 16) if discovery_info.pid else 0
        except (ValueError, TypeError):
            vendor_id, product_id = 0, 0

        if not vendor_id or not product_id:
            return self.async_abort(reason="invalid_discovery_info")

        # Set unique ID (includes serial if available to distinguish identical printers)
        serial_number = discovery_info.serial_number
        unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

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
                return await self.async_step_custom_profile()

            return await self.async_step_codepage()

        # Build profile choices dynamically
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        printer_name = self._user_data.get("_printer_name", "USB Printer")

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_PROFILE, default=PROFILE_AUTO): vol.In(profile_choices),
            }
        )

        return self.async_show_form(
            step_id="usb_confirm",
            data_schema=data_schema,
            description_placeholders={"printer_name": printer_name},
        )

    async def async_step_custom_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle custom profile name entry.

        Args:
            user_input: User provided profile name

        Returns:
            FlowResult for next step
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            custom_profile = user_input.get("custom_profile", "").strip()
            _LOGGER.debug("Custom profile entered: %s", custom_profile)

            # Validate the profile exists in escpos-printer-db
            is_valid = await self.hass.async_add_executor_job(
                is_valid_profile, custom_profile
            )
            if not custom_profile or not is_valid:
                _LOGGER.warning("Invalid profile name: %s", custom_profile)
                errors["base"] = "invalid_profile"
            else:
                self._user_data[CONF_PROFILE] = custom_profile
                return await self.async_step_codepage()

        data_schema = vol.Schema(
            {
                vol.Required("custom_profile"): str,
            }
        )

        return self.async_show_form(
            step_id="custom_profile",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_codepage(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle step 2: Codepage and settings selection.

        Args:
            user_input: User provided settings

        Returns:
            FlowResult with entry creation or custom step
        """
        if user_input is not None:
            _LOGGER.debug("Config flow codepage step input: %s", user_input)

            codepage = user_input.get(CONF_CODEPAGE, "")
            line_width = user_input.get(CONF_LINE_WIDTH)

            # Handle custom codepage
            if codepage == OPTION_CUSTOM:
                # Store current selections and go to custom codepage step
                self._user_data[CONF_DEFAULT_ALIGN] = user_input.get(
                    CONF_DEFAULT_ALIGN, DEFAULT_ALIGN
                )
                self._user_data[CONF_DEFAULT_CUT] = user_input.get(
                    CONF_DEFAULT_CUT, DEFAULT_CUT
                )
                self._user_data[CONF_LINE_WIDTH] = (
                    int(line_width) if line_width and line_width != OPTION_CUSTOM else DEFAULT_LINE_WIDTH
                )
                return await self.async_step_custom_codepage()

            # Handle custom line width
            if line_width == OPTION_CUSTOM:
                # Store current selections and go to custom line width step
                self._user_data[CONF_CODEPAGE] = codepage if codepage else ""
                self._user_data[CONF_DEFAULT_ALIGN] = user_input.get(
                    CONF_DEFAULT_ALIGN, DEFAULT_ALIGN
                )
                self._user_data[CONF_DEFAULT_CUT] = user_input.get(
                    CONF_DEFAULT_CUT, DEFAULT_CUT
                )
                return await self.async_step_custom_line_width()

            # Merge with data from previous steps and create entry
            data = {
                **self._user_data,
                CONF_CODEPAGE: codepage if codepage else "",
                CONF_LINE_WIDTH: int(line_width) if line_width else DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: user_input.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                CONF_DEFAULT_CUT: user_input.get(CONF_DEFAULT_CUT, DEFAULT_CUT),
            }

            # Remove internal keys
            data.pop("_printer_name", None)

            # Generate title based on connection type
            connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
            if connection_type == CONNECTION_TYPE_USB:
                title = self._user_data.get(
                    "_printer_name",
                    f"USB Printer {data.get(CONF_VENDOR_ID, 0):04X}:{data.get(CONF_PRODUCT_ID, 0):04X}"
                )
            else:
                host = data[CONF_HOST]
                port = data[CONF_PORT]
                title = f"{host}:{port}"

            _LOGGER.debug(
                "Creating config entry for %s with profile=%s codepage=%s",
                title,
                data.get(CONF_PROFILE),
                data.get(CONF_CODEPAGE),
            )

            return self.async_create_entry(title=title, data=data)

        # Get profile-specific options
        profile = self._user_data.get(CONF_PROFILE, PROFILE_AUTO)

        # Get codepages for selected profile
        codepage_list = await self.hass.async_add_executor_job(
            get_profile_codepages, profile
        )
        codepage_choices: dict[str, str] = {"": "(Default - Auto)"}
        codepage_choices.update({cp: cp for cp in codepage_list})
        codepage_choices[OPTION_CUSTOM] = "Custom (enter codepage)..."

        # Get line widths for selected profile
        width_list = await self.hass.async_add_executor_job(
            get_profile_line_widths, profile
        )
        width_choices: dict[str | int, str] = {}
        for w in width_list:
            width_choices[w] = f"{w} columns"
        width_choices[OPTION_CUSTOM] = "Custom (enter columns)..."

        # Get cut modes for selected profile
        cut_modes = await self.hass.async_add_executor_job(get_profile_cut_modes, profile)
        cut_choices = {m: m.title() for m in cut_modes}

        data_schema = vol.Schema(
            {
                vol.Optional(CONF_CODEPAGE, default=""): vol.In(codepage_choices),
                vol.Optional(CONF_LINE_WIDTH, default=DEFAULT_LINE_WIDTH): vol.In(
                    width_choices
                ),
                vol.Optional(CONF_DEFAULT_ALIGN, default=DEFAULT_ALIGN): vol.In(
                    ["left", "center", "right"]
                ),
                vol.Optional(CONF_DEFAULT_CUT, default=DEFAULT_CUT): vol.In(cut_choices),
            }
        )

        return self.async_show_form(step_id="codepage", data_schema=data_schema)

    async def async_step_custom_codepage(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle custom codepage entry.

        Args:
            user_input: User provided codepage

        Returns:
            FlowResult for entry creation or line width step
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            custom_codepage = user_input.get("custom_codepage", "").strip()
            _LOGGER.debug("Custom codepage entered: %s", custom_codepage)

            # Validate the codepage
            profile = self._user_data.get(CONF_PROFILE)
            is_valid = await self.hass.async_add_executor_job(
                is_valid_codepage_for_profile, custom_codepage, profile
            )
            if not custom_codepage or not is_valid:
                _LOGGER.warning("Invalid codepage: %s", custom_codepage)
                errors["base"] = "invalid_codepage"
            else:
                # Check if we still need custom line width
                line_width = self._user_data.get(CONF_LINE_WIDTH)
                if line_width == OPTION_CUSTOM or line_width is None:
                    self._user_data[CONF_CODEPAGE] = custom_codepage
                    return await self.async_step_custom_line_width()

                # Create entry
                data = {
                    **self._user_data,
                    CONF_CODEPAGE: custom_codepage,
                }

                # Remove internal keys
                data.pop("_printer_name", None)

                # Generate title based on connection type
                connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
                if connection_type == CONNECTION_TYPE_USB:
                    title = self._user_data.get(
                        "_printer_name",
                        f"USB Printer {data.get(CONF_VENDOR_ID, 0):04X}:{data.get(CONF_PRODUCT_ID, 0):04X}"
                    )
                else:
                    host = data[CONF_HOST]
                    port = data[CONF_PORT]
                    title = f"{host}:{port}"

                return self.async_create_entry(title=title, data=data)

        data_schema = vol.Schema(
            {
                vol.Required("custom_codepage"): str,
            }
        )

        return self.async_show_form(
            step_id="custom_codepage",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_custom_line_width(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle custom line width entry.

        Args:
            user_input: User provided line width

        Returns:
            FlowResult for entry creation
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            custom_width = user_input.get("custom_line_width")
            _LOGGER.debug("Custom line width entered: %s", custom_width)

            # Validate line width is a positive number within reasonable bounds
            try:
                width_int = int(custom_width)  # type: ignore[arg-type]
                if width_int < 1 or width_int > 255:
                    _LOGGER.warning("Invalid line width (out of range): %s", custom_width)
                    errors["base"] = "invalid_line_width"
            except (ValueError, TypeError):
                _LOGGER.warning("Invalid line width (not a number): %s", custom_width)
                errors["base"] = "invalid_line_width"

            if not errors:
                # Create entry
                data = {
                    **self._user_data,
                    CONF_LINE_WIDTH: width_int,
                }

                # Remove internal keys
                data.pop("_printer_name", None)

                # Generate title based on connection type
                connection_type = data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
                if connection_type == CONNECTION_TYPE_USB:
                    title = self._user_data.get(
                        "_printer_name",
                        f"USB Printer {data.get(CONF_VENDOR_ID, 0):04X}:{data.get(CONF_PRODUCT_ID, 0):04X}"
                    )
                else:
                    host = data[CONF_HOST]
                    port = data[CONF_PORT]
                    title = f"{host}:{port}"

                return self.async_create_entry(title=title, data=data)

        data_schema = vol.Schema(
            {
                vol.Required("custom_line_width", default=DEFAULT_LINE_WIDTH): int,
            }
        )

        return self.async_show_form(
            step_id="custom_line_width",
            data_schema=data_schema,
            errors=errors,
        )

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Support YAML import if provided.

        Args:
            user_input: YAML configuration data

        Returns:
            FlowResult
        """
        _LOGGER.debug("Config flow import step with input: %s", user_input)

        if not user_input:
            return await self.async_step_network(None)

        # Default to network type if not specified
        connection_type = user_input.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)
        user_input[CONF_CONNECTION_TYPE] = connection_type

        if connection_type == CONNECTION_TYPE_USB:
            # USB YAML import - create entry directly if all required fields present
            raw_vid = user_input.get(CONF_VENDOR_ID)
            raw_pid = user_input.get(CONF_PRODUCT_ID)

            if not raw_vid or not raw_pid:
                _LOGGER.error("USB YAML import missing vendor_id or product_id")
                return self.async_abort(reason="invalid_usb_device")

            # Coerce VID/PID to integers - handle strings like "0x04b8", "04b8", or "1208"
            try:
                vendor_id = _parse_vid_pid(raw_vid)
                product_id = _parse_vid_pid(raw_pid)
            except (ValueError, TypeError) as ex:
                _LOGGER.error("USB YAML import invalid vendor_id or product_id: %s", ex)
                return self.async_abort(reason="invalid_usb_device")

            # Validate VID/PID range
            if not (0x0001 <= vendor_id <= 0xFFFF) or not (0x0001 <= product_id <= 0xFFFF):
                _LOGGER.error("USB YAML import VID/PID out of range: %s/%s", vendor_id, product_id)
                return self.async_abort(reason="invalid_usb_device")

            # Set unique ID only if serial_number provided (allows multiple identical printers)
            serial_number = user_input.get("serial_number")
            if serial_number:
                unique_id = _generate_usb_unique_id(vendor_id, product_id, serial_number)
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
            # Note: Without serial_number, no unique_id is set - duplicates allowed

            # Build complete entry data with defaults
            data = {
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: vendor_id,
                CONF_PRODUCT_ID: product_id,
                CONF_IN_EP: user_input.get(CONF_IN_EP, DEFAULT_IN_EP),
                CONF_OUT_EP: user_input.get(CONF_OUT_EP, DEFAULT_OUT_EP),
                CONF_TIMEOUT: user_input.get(CONF_TIMEOUT, DEFAULT_TIMEOUT),
                CONF_PROFILE: user_input.get(CONF_PROFILE, PROFILE_AUTO),
                CONF_CODEPAGE: user_input.get(CONF_CODEPAGE, ""),
                CONF_LINE_WIDTH: user_input.get(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH),
                CONF_DEFAULT_ALIGN: user_input.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                CONF_DEFAULT_CUT: user_input.get(CONF_DEFAULT_CUT, DEFAULT_CUT),
            }

            title = f"USB Printer {vendor_id:04X}:{product_id:04X}"
            return self.async_create_entry(title=title, data=data)

        # Network import - use existing flow
        return await self.async_step_network(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        """Create options flow handler.

        Args:
            config_entry: Config entry to be configured

        Returns:
            Options flow handler instance
        """
        # Import here to avoid circular imports
        from .options_flow import EscposOptionsFlowHandler  # noqa: PLC0415

        return EscposOptionsFlowHandler(config_entry)
