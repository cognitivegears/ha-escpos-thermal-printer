"""Tests for ESC/POS Thermal Printer config flow."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT

from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONNECTION_TYPE_NETWORK,
    DEFAULT_LINE_WIDTH,
    DOMAIN,
)


async def test_config_flow_success(hass):  # type: ignore[no-untyped-def]
    """Test successful three-step config flow for network printer."""
    with patch(
        "custom_components.escpos_printer.config_flow.main_flow._can_connect", return_value=True
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Select network connection type
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )

        # Should move to network step
        assert result2["type"] == "form"
        assert result2["step_id"] == "network"

        # Step 2: Network configuration
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        )

        # Should move to codepage step
        assert result3["type"] == "form"
        assert result3["step_id"] == "codepage"

        # Step 3: Codepage step - encoding settings
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "",  # Default
                CONF_LINE_WIDTH: DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        # Should create entry
        assert result4["type"] == "create_entry"
        assert result4["data"][CONF_HOST] == "1.2.3.4"
        assert result4["data"][CONF_PORT] == 9100
        assert result4["data"].get(CONF_PROFILE) == ""  # Auto-detect default
        assert result4["data"].get(CONF_CODEPAGE) == ""
        assert result4["data"].get(CONF_LINE_WIDTH) == DEFAULT_LINE_WIDTH
        assert result4["data"].get(CONF_CONNECTION_TYPE) == CONNECTION_TYPE_NETWORK


async def test_config_flow_connection_failure(hass):  # type: ignore[no-untyped-def]
    """Test config flow with connection failure."""
    with patch(
        "custom_components.escpos_printer.config_flow.main_flow._can_connect", return_value=False
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Select network connection type
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )

        # Should move to network step
        assert result2["type"] == "form"
        assert result2["step_id"] == "network"

        # Step 2: Network configuration (will fail)
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        )

        # Should show form again with error
        assert result3["type"] == "form"
        assert result3["step_id"] == "network"
        assert result3["errors"]["base"] == "cannot_connect"


async def test_config_flow_with_profile_selection(hass):  # type: ignore[no-untyped-def]
    """Test config flow with profile selection."""
    with patch(
        "custom_components.escpos_printer.config_flow.main_flow._can_connect", return_value=True
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )

        # Step 2: Network configuration with profile
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100, CONF_PROFILE: "default"},
        )

        assert result3["type"] == "form"
        assert result3["step_id"] == "codepage"

        # Complete with defaults
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "CP437",
                CONF_LINE_WIDTH: 48,
                CONF_DEFAULT_ALIGN: "center",
                CONF_DEFAULT_CUT: "partial",
            },
        )

        assert result4["type"] == "create_entry"
        assert result4["data"][CONF_PROFILE] == "default"
        assert result4["data"][CONF_CODEPAGE] == "CP437"
        assert result4["data"][CONF_LINE_WIDTH] == 48
        assert result4["data"][CONF_DEFAULT_ALIGN] == "center"
        assert result4["data"][CONF_DEFAULT_CUT] == "partial"


async def test_config_flow_custom_profile(hass):  # type: ignore[no-untyped-def]
    """Test config flow with custom profile entry."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.main_flow._can_connect", return_value=True
        ),
        patch(
            "custom_components.escpos_printer.config_flow.main_flow.is_valid_profile", return_value=True
        ),
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )

        # Step 2: Network configuration with custom profile
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100, CONF_PROFILE: "__custom__"},
        )

        # Should show custom profile form
        assert result3["type"] == "form"
        assert result3["step_id"] == "custom_profile"

        # Enter custom profile name
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {"custom_profile": "TM-T88V"},
        )

        # Should move to codepage step
        assert result4["type"] == "form"
        assert result4["step_id"] == "codepage"

        # Complete the flow
        result5 = await hass.config_entries.flow.async_configure(
            result4["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        assert result5["type"] == "create_entry"
        assert result5["data"][CONF_PROFILE] == "TM-T88V"


async def test_config_flow_custom_codepage(hass):  # type: ignore[no-untyped-def]
    """Test config flow with custom codepage entry."""
    with (
        patch(
            "custom_components.escpos_printer.config_flow.main_flow._can_connect", return_value=True
        ),
        patch(
            "custom_components.escpos_printer.config_flow.main_flow.is_valid_codepage_for_profile",
            return_value=True,
        ),
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )

        # Step 2: Network configuration
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        )

        # Select custom codepage
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "__custom__",
                CONF_LINE_WIDTH: DEFAULT_LINE_WIDTH,
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        # Should show custom codepage form
        assert result4["type"] == "form"
        assert result4["step_id"] == "custom_codepage"

        # Enter custom codepage
        result5 = await hass.config_entries.flow.async_configure(
            result4["flow_id"],
            {"custom_codepage": "CP932"},
        )

        assert result5["type"] == "create_entry"
        assert result5["data"][CONF_CODEPAGE] == "CP932"


async def test_config_flow_custom_line_width(hass):  # type: ignore[no-untyped-def]
    """Test config flow with custom line width entry."""
    with patch(
        "custom_components.escpos_printer.config_flow.main_flow._can_connect", return_value=True
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK},
        )

        # Step 2: Network configuration
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        )

        # Select custom line width
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: "__custom__",
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )

        # Should show custom line width form
        assert result4["type"] == "form"
        assert result4["step_id"] == "custom_line_width"

        # Enter custom line width
        result5 = await hass.config_entries.flow.async_configure(
            result4["flow_id"],
            {"custom_line_width": 80},
        )

        assert result5["type"] == "create_entry"
        assert result5["data"][CONF_LINE_WIDTH] == 80
