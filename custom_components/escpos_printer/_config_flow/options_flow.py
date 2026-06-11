"""Options flow handler for ESC/POS Thermal Printer integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
import voluptuous as vol

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
    CONF_ALLOW_LOCAL_IMAGE_URLS,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_KEEPALIVE,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_RELIABILITY_PROFILE,
    CONF_STATUS_INTERVAL,
    CONF_TIMEOUT,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
    DEFAULT_ALIGN,
    DEFAULT_ALLOW_LOCAL_IMAGE_URLS,
    DEFAULT_CUT,
    DEFAULT_LINE_WIDTH,
    DEFAULT_TIMEOUT,
    RELIABILITY_PROFILE_AUTO,
    RELIABILITY_PROFILE_BALANCED,
    RELIABILITY_PROFILE_BLUETOOTH,
    RELIABILITY_PROFILE_CONSERVATIVE,
    RELIABILITY_PROFILE_FAST_LAN,
)

_RELIABILITY_LABELS: dict[str, str] = {
    RELIABILITY_PROFILE_AUTO: "Auto (recommended)",
    RELIABILITY_PROFILE_FAST_LAN: "Fast LAN (Epson TM-T20/T88, 0 ms delay)",
    RELIABILITY_PROFILE_BALANCED: "Balanced (most USB / Star TSP)",
    RELIABILITY_PROFILE_CONSERVATIVE: "Conservative (cheap POS-58/80)",
    RELIABILITY_PROFILE_BLUETOOTH: "Bluetooth-safe (slow SPP printers)",
}

_LOGGER = logging.getLogger(__name__)


class EscposOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Options flow handler for ESC/POS Thermal Printer.

    Extends ``OptionsFlowWithReload`` so HA reloads the entry automatically
    when the options actually change (the integration reads its options
    only in ``async_setup_entry``). This is the modern replacement for a
    manual ``add_update_listener`` and, unlike that listener, does NOT
    reload on a no-op save.

    Modern HA (>= 2024.11; this project pins >= 2026.3) injects
    ``config_entry`` via the base class. B-M1: the 2024.8-2024.10
    compatibility shim that previously stored a parallel
    ``_config_entry_compat`` via ``object.__setattr__`` has been removed
    now that the supported HA floor moved past the breaking point.
    """

    def __init__(self) -> None:
        """Initialize the options flow handler.

        Takes no arguments — modern HA framework injects ``config_entry``
        onto the instance via the ``OptionsFlow`` base class.
        """
        self._pending_data: dict[str, Any] = {}
        super().__init__()

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the options flow initialization.

        Args:
            user_input: User provided options data

        Returns:
            FlowResult containing the next step or final result
        """
        if user_input is not None:
            _LOGGER.debug(
                "Options flow update for entry %s: %s",
                self.config_entry.entry_id,
                user_input,
            )

            # Check for custom options
            profile = user_input.get(CONF_PROFILE)
            codepage = user_input.get(CONF_CODEPAGE)
            line_width = user_input.get(CONF_LINE_WIDTH)

            # Handle profile change - reset dependent options
            old_profile = self.config_entry.options.get(CONF_PROFILE) or self.config_entry.data.get(
                CONF_PROFILE, PROFILE_AUTO
            )

            if profile not in (old_profile, PROFILE_CUSTOM):
                _LOGGER.info(
                    "Profile changed from %s to %s, resetting dependent options",
                    old_profile,
                    profile,
                )
                user_input[CONF_CODEPAGE] = ""
                codepage = ""
                # Line width and cut mode will be reset to profile defaults

            # Handle custom profile
            if profile == PROFILE_CUSTOM:
                self._pending_data = dict(user_input)
                return await self.async_step_custom_profile()

            # Handle custom codepage
            if codepage == OPTION_CUSTOM:
                self._pending_data = dict(user_input)
                return await self.async_step_custom_codepage()

            # Handle custom line width
            if line_width == OPTION_CUSTOM:
                self._pending_data = dict(user_input)
                return await self.async_step_custom_line_width()

            return self.async_create_entry(title="Options", data=user_input)

        # Get current values
        current_profile = self.config_entry.options.get(CONF_PROFILE) or self.config_entry.data.get(
            CONF_PROFILE, PROFILE_AUTO
        )
        current_codepage = self.config_entry.options.get(
            CONF_CODEPAGE
        ) or self.config_entry.data.get(CONF_CODEPAGE, "")
        current_line_width = self.config_entry.options.get(
            CONF_LINE_WIDTH
        ) or self.config_entry.data.get(CONF_LINE_WIDTH, DEFAULT_LINE_WIDTH)

        # Get profile choices
        profile_choices = await self.hass.async_add_executor_job(get_profile_choices_dict)

        # Ensure current profile is in choices (backward compatibility)
        if current_profile and current_profile not in profile_choices:
            profile_choices[current_profile] = f"{current_profile} (current)"

        # Get codepages for current profile
        codepage_list = await self.hass.async_add_executor_job(
            get_profile_codepages, current_profile
        )
        codepage_choices: dict[str, str] = {"": "(Default - Auto)"}
        codepage_choices.update({cp: cp for cp in codepage_list})
        codepage_choices[OPTION_CUSTOM] = "Custom (enter codepage)..."

        # Ensure current codepage is in choices (backward compatibility)
        if current_codepage and current_codepage not in codepage_choices:
            codepage_choices[current_codepage] = f"{current_codepage} (current)"

        # Get line widths for current profile. String keys are required because
        # the HA frontend submits all dropdown values as strings; integer keys
        # cause vol.In to fail ("42" not in {42, 56, ...}).
        width_list = await self.hass.async_add_executor_job(
            get_profile_line_widths, current_profile
        )
        width_choices: dict[str, str] = {}
        for w in width_list:
            width_choices[str(w)] = f"{w} columns"
        width_choices[OPTION_CUSTOM] = "Custom (enter columns)..."

        # Ensure current line width is in choices (backward compatibility).
        # Normalise to str so the lookup works regardless of stored type.
        current_line_width_str = str(current_line_width)
        if current_line_width_str not in width_choices:
            width_choices[current_line_width_str] = f"{current_line_width} columns (current)"

        # Get cut modes for current profile
        cut_modes = await self.hass.async_add_executor_job(get_profile_cut_modes, current_profile)
        cut_choices = {m: m.title() for m in cut_modes}

        # Ensure current cut mode is in choices
        current_cut = self.config_entry.options.get(CONF_DEFAULT_CUT) or self.config_entry.data.get(
            CONF_DEFAULT_CUT, DEFAULT_CUT
        )
        if current_cut not in cut_choices:
            cut_choices[current_cut] = f"{current_cut.title()} (current)"

        # Check connection type to show appropriate options
        connection_type = self.config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_TYPE_NETWORK)

        # Reliability profile: defaults to "auto" for new entries.
        # Bluetooth defaults to "bluetooth_safe" since SPP transports
        # need the throttle on first use; the user can still pick auto
        # if their hardware is fast enough.
        current_reliability = self.config_entry.options.get(
            CONF_RELIABILITY_PROFILE,
            RELIABILITY_PROFILE_BLUETOOTH
            if connection_type == CONNECTION_TYPE_BLUETOOTH
            else RELIABILITY_PROFILE_AUTO,
        )
        reliability_choices = dict(_RELIABILITY_LABELS)

        # Build schema - USB and serial printers don't have keepalive option
        if connection_type in (CONNECTION_TYPE_USB, CONNECTION_TYPE_SERIAL):
            data_schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_TIMEOUT, self.config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(CONF_PROFILE, default=current_profile): vol.In(profile_choices),
                    vol.Optional(CONF_CODEPAGE, default=current_codepage): vol.In(codepage_choices),
                    vol.Optional(CONF_LINE_WIDTH, default=current_line_width_str): vol.In(
                        width_choices
                    ),
                    vol.Optional(
                        CONF_DEFAULT_ALIGN,
                        default=self.config_entry.options.get(
                            CONF_DEFAULT_ALIGN,
                            self.config_entry.data.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                        ),
                    ): vol.In(["left", "center", "right"]),
                    vol.Optional(CONF_DEFAULT_CUT, default=current_cut): vol.In(cut_choices),
                    vol.Optional(CONF_RELIABILITY_PROFILE, default=current_reliability): vol.In(
                        reliability_choices
                    ),
                    vol.Optional(
                        CONF_STATUS_INTERVAL,
                        default=self.config_entry.options.get(CONF_STATUS_INTERVAL, 0),
                    ): int,
                    vol.Optional(
                        CONF_ALLOW_LOCAL_IMAGE_URLS,
                        default=self.config_entry.options.get(
                            CONF_ALLOW_LOCAL_IMAGE_URLS, DEFAULT_ALLOW_LOCAL_IMAGE_URLS
                        ),
                    ): bool,
                }
            )
        else:
            data_schema = vol.Schema(
                {
                    vol.Optional(
                        CONF_TIMEOUT,
                        default=self.config_entry.options.get(
                            CONF_TIMEOUT, self.config_entry.data.get(CONF_TIMEOUT, DEFAULT_TIMEOUT)
                        ),
                    ): vol.Coerce(float),
                    vol.Optional(CONF_PROFILE, default=current_profile): vol.In(profile_choices),
                    vol.Optional(CONF_CODEPAGE, default=current_codepage): vol.In(codepage_choices),
                    vol.Optional(CONF_LINE_WIDTH, default=current_line_width_str): vol.In(
                        width_choices
                    ),
                    vol.Optional(
                        CONF_DEFAULT_ALIGN,
                        default=self.config_entry.options.get(
                            CONF_DEFAULT_ALIGN,
                            self.config_entry.data.get(CONF_DEFAULT_ALIGN, DEFAULT_ALIGN),
                        ),
                    ): vol.In(["left", "center", "right"]),
                    vol.Optional(CONF_DEFAULT_CUT, default=current_cut): vol.In(cut_choices),
                    vol.Optional(CONF_RELIABILITY_PROFILE, default=current_reliability): vol.In(
                        reliability_choices
                    ),
                    vol.Optional(
                        CONF_KEEPALIVE,
                        default=self.config_entry.options.get(CONF_KEEPALIVE, False),
                    ): bool,
                    vol.Optional(
                        CONF_STATUS_INTERVAL,
                        default=self.config_entry.options.get(CONF_STATUS_INTERVAL, 0),
                    ): int,
                    vol.Optional(
                        CONF_ALLOW_LOCAL_IMAGE_URLS,
                        default=self.config_entry.options.get(
                            CONF_ALLOW_LOCAL_IMAGE_URLS, DEFAULT_ALLOW_LOCAL_IMAGE_URLS
                        ),
                    ): bool,
                }
            )

        _LOGGER.debug("Showing options form for entry %s", self.config_entry.entry_id)
        return self.async_show_form(step_id="init", data_schema=data_schema)

    async def async_step_custom_profile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle custom profile name entry in options flow.

        Args:
            user_input: User provided profile name

        Returns:
            FlowResult for next step or entry creation
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            custom_profile = user_input.get("custom_profile", "").strip()
            _LOGGER.debug("Options: Custom profile entered: %s", custom_profile)

            # Validate the profile exists in escpos-printer-db
            is_valid = await self.hass.async_add_executor_job(is_valid_profile, custom_profile)
            if not custom_profile or not is_valid:
                _LOGGER.warning("Invalid profile name: %s", custom_profile)
                errors["base"] = "invalid_profile"
            else:
                data = dict(self._pending_data)
                data[CONF_PROFILE] = custom_profile

                # Check if codepage or line width also need custom entry
                if data.get(CONF_CODEPAGE) == OPTION_CUSTOM:
                    self._pending_data = data
                    return await self.async_step_custom_codepage()

                if data.get(CONF_LINE_WIDTH) == OPTION_CUSTOM:
                    self._pending_data = data
                    return await self.async_step_custom_line_width()

                return self.async_create_entry(title="Options", data=data)

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

    async def async_step_custom_codepage(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle custom codepage entry in options flow.

        Args:
            user_input: User provided codepage

        Returns:
            FlowResult for next step or entry creation
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            custom_codepage = user_input.get("custom_codepage", "").strip()
            _LOGGER.debug("Options: Custom codepage entered: %s", custom_codepage)

            # Validate the codepage
            profile = self._pending_data.get(CONF_PROFILE)
            is_valid = await self.hass.async_add_executor_job(
                is_valid_codepage_for_profile, custom_codepage, profile
            )
            if not custom_codepage or not is_valid:
                _LOGGER.warning("Invalid codepage: %s", custom_codepage)
                errors["base"] = "invalid_codepage"
            else:
                data = dict(self._pending_data)
                data[CONF_CODEPAGE] = custom_codepage

                # Check if line width also needs custom entry
                if data.get(CONF_LINE_WIDTH) == OPTION_CUSTOM:
                    self._pending_data = data
                    return await self.async_step_custom_line_width()

                return self.async_create_entry(title="Options", data=data)

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
        """Handle custom line width entry in options flow.

        Args:
            user_input: User provided line width

        Returns:
            FlowResult for entry creation
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            custom_width = user_input.get("custom_line_width")
            _LOGGER.debug("Options: Custom line width entered: %s", custom_width)

            from .network_helpers import validate_custom_line_width  # noqa: PLC0415

            width_int, err_code = validate_custom_line_width(custom_width)
            if err_code:
                errors["base"] = err_code

            if not errors and width_int is not None:
                data = dict(self._pending_data)
                data[CONF_LINE_WIDTH] = width_int

                return self.async_create_entry(title="Options", data=data)

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
