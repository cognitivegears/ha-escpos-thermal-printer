"""Settings configuration steps mixin (profile, codepage, line width)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

from ..capabilities import (
    OPTION_CUSTOM,
    PROFILE_AUTO,
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
    CONF_HOST,
    CONF_LINE_WIDTH,
    CONF_PORT,
    CONF_PRODUCT_ID,
    CONF_PROFILE,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DEFAULT_ALIGN,
    DEFAULT_CUT,
    DEFAULT_LINE_WIDTH,
)

_LOGGER = logging.getLogger(__name__)


class SettingsFlowMixin:
    """Mixin providing settings configuration steps.

    This mixin expects to be used with a class that has the following attributes
    and methods (typically provided by ConfigFlow):
    - hass: HomeAssistant instance
    - _user_data: dict for storing flow data
    - async_show_form(): Show a form to the user
    - async_create_entry(): Create the config entry
    """

    # These attributes are expected from the main flow class
    hass: Any
    _user_data: dict[str, Any]

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

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
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

            return self.async_create_entry(title=title, data=data)  # type: ignore[attr-defined,no-any-return]

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

        return self.async_show_form(step_id="codepage", data_schema=data_schema)  # type: ignore[attr-defined,no-any-return]

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

                return self.async_create_entry(title=title, data=data)  # type: ignore[attr-defined,no-any-return]

        data_schema = vol.Schema(
            {
                vol.Required("custom_codepage"): str,
            }
        )

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
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

                return self.async_create_entry(title=title, data=data)  # type: ignore[attr-defined,no-any-return]

        data_schema = vol.Schema(
            {
                vol.Required("custom_line_width", default=DEFAULT_LINE_WIDTH): int,
            }
        )

        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="custom_line_width",
            data_schema=data_schema,
            errors=errors,
        )
