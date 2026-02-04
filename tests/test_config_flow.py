"""Tests for ESC/POS Thermal Printer config flow."""

from unittest.mock import patch

from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_LINE_WIDTH,
    CONF_PRINTER_NAME,
    CONF_PROFILE,
    DEFAULT_LINE_WIDTH,
    DOMAIN,
)


async def test_config_flow_success(hass):  # type: ignore[no-untyped-def]
    """Test successful two-step config flow."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter", "OtherPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=True,
        ),
    ):
        # Step 1: User step - CUPS printer selection and profile
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter"},
        )

        # Should move to codepage step
        assert result2["type"] == "form"
        assert result2["step_id"] == "codepage"

        # Step 2: Codepage step - encoding settings
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_CODEPAGE: "",  # Default
                CONF_LINE_WIDTH: DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        # Should create entry
        assert result3["type"] == "create_entry"
        assert result3["data"][CONF_PRINTER_NAME] == "TestPrinter"
        assert result3["data"].get(CONF_PROFILE) == ""  # Auto-detect default
        assert result3["data"].get(CONF_CODEPAGE) == ""
        assert result3["data"].get(CONF_LINE_WIDTH) == DEFAULT_LINE_WIDTH


async def test_config_flow_connection_failure(hass):  # type: ignore[no-untyped-def]
    """Test config flow with connection failure."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=False,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter"},
        )

        # Should show form again with error
        assert result2["type"] == "form"
        assert result2["step_id"] == "user"
        assert result2["errors"]["base"] == "cannot_connect"


async def test_config_flow_with_profile_selection(hass):  # type: ignore[no-untyped-def]
    """Test config flow with profile selection."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        # Configure with a profile (using fallback 'default' profile)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter", CONF_PROFILE: "default"},
        )

        assert result2["type"] == "form"
        assert result2["step_id"] == "codepage"

        # Complete with defaults
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_CODEPAGE: "CP437",
                CONF_LINE_WIDTH: 48,
                CONF_DEFAULT_ALIGN: "center",
                CONF_DEFAULT_CUT: "partial",
            },
        )

        assert result3["type"] == "create_entry"
        assert result3["data"][CONF_PROFILE] == "default"
        assert result3["data"][CONF_CODEPAGE] == "CP437"
        assert result3["data"][CONF_LINE_WIDTH] == 48
        assert result3["data"][CONF_DEFAULT_ALIGN] == "center"
        assert result3["data"][CONF_DEFAULT_CUT] == "partial"


async def test_config_flow_custom_profile(hass):  # type: ignore[no-untyped-def]
    """Test config flow with custom profile entry."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_valid_profile", return_value=True
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        # Select custom profile
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter", CONF_PROFILE: "__custom__"},
        )

        # Should show custom profile form
        assert result2["type"] == "form"
        assert result2["step_id"] == "custom_profile"

        # Enter custom profile name
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {"custom_profile": "TM-T88V"},
        )

        # Should move to codepage step
        assert result3["type"] == "form"
        assert result3["step_id"] == "codepage"

        # Complete the flow
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        assert result4["type"] == "create_entry"
        assert result4["data"][CONF_PROFILE] == "TM-T88V"


async def test_config_flow_custom_codepage(hass):  # type: ignore[no-untyped-def]
    """Test config flow with custom codepage entry."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_valid_codepage_for_profile",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter"},
        )

        # Select custom codepage
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_CODEPAGE: "__custom__",
                CONF_LINE_WIDTH: DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        # Should show custom codepage form
        assert result3["type"] == "form"
        assert result3["step_id"] == "custom_codepage"

        # Enter custom codepage
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {"custom_codepage": "CP932"},
        )

        assert result4["type"] == "create_entry"
        assert result4["data"][CONF_CODEPAGE] == "CP932"


async def test_config_flow_custom_line_width(hass):  # type: ignore[no-untyped-def]
    """Test config flow with custom line width entry."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer.config_flow.is_cups_printer_available",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter"},
        )

        # Select custom line width
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: "__custom__",
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        # Should show custom line width form
        assert result3["type"] == "form"
        assert result3["step_id"] == "custom_line_width"

        # Enter custom line width
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {"custom_line_width": 80},
        )

        assert result4["type"] == "create_entry"
        assert result4["data"][CONF_LINE_WIDTH] == 80
