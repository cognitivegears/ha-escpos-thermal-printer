"""Tests for CUPS config flow steps."""

from unittest.mock import patch

from custom_components.escpos_printer._config_flow.entry_helpers import (
    generate_entry_title,
)
from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_CUPS_SERVER,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_LINE_WIDTH,
    CONF_PRINTER_NAME,
    CONF_PROFILE,
    CONNECTION_TYPE_CUPS,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DEFAULT_LINE_WIDTH,
    DOMAIN,
)


async def test_cups_config_flow_success(hass):  # type: ignore[no-untyped-def]
    """Test successful CUPS config flow: user -> cups -> cups_printer -> codepage -> create."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.get_cups_printers",
            return_value=["TestPrinter", "OtherPrinter"],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_printer_available",
            return_value=True,
        ),
    ):
        # Step 1: Connection type selection
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        # Select CUPS connection type
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS},
        )
        assert result2["type"] == "form"
        assert result2["step_id"] == "cups"

        # Step 2: CUPS server (empty = localhost)
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_CUPS_SERVER: ""},
        )
        assert result3["type"] == "form"
        assert result3["step_id"] == "cups_printer"

        # Step 3: Select printer
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter"},
        )
        assert result4["type"] == "form"
        assert result4["step_id"] == "codepage"

        # Step 4: Codepage/settings
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
        assert result5["title"] == "TestPrinter"
        assert result5["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_CUPS
        assert result5["data"][CONF_PRINTER_NAME] == "TestPrinter"
        assert result5["data"][CONF_CUPS_SERVER] is None
        assert result5["data"].get(CONF_PROFILE) == ""


async def test_cups_config_flow_remote_server(hass):  # type: ignore[no-untyped-def]
    """Test CUPS config flow with remote server."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.get_cups_printers",
            return_value=["RemotePrinter"],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_printer_available",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS},
        )

        # Enter remote server
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_CUPS_SERVER: "printserver.local"},
        )
        assert result3["type"] == "form"
        assert result3["step_id"] == "cups_printer"

        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {CONF_PRINTER_NAME: "RemotePrinter"},
        )
        assert result4["type"] == "form"
        assert result4["step_id"] == "codepage"

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
        assert result5["title"] == "RemotePrinter"
        assert result5["data"][CONF_CUPS_SERVER] == "printserver.local"
        assert result5["data"][CONF_PRINTER_NAME] == "RemotePrinter"


async def test_cups_config_flow_server_unavailable(hass):  # type: ignore[no-untyped-def]
    """Test CUPS config flow when server is not available."""
    with patch(
        "custom_components.escpos_printer._config_flow.cups_steps.is_cups_available",
        return_value=False,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS},
        )

        # Try to connect to unavailable server
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_CUPS_SERVER: "bad-server"},
        )
        assert result3["type"] == "form"
        assert result3["step_id"] == "cups"
        assert result3["errors"]["base"] == "cups_unavailable"


async def test_cups_config_flow_no_printers(hass):  # type: ignore[no-untyped-def]
    """Test CUPS config flow when no printers are found."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.get_cups_printers",
            return_value=[],
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS},
        )
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_CUPS_SERVER: ""},
        )
        assert result3["type"] == "form"
        assert result3["step_id"] == "cups_printer"
        assert result3["errors"]["base"] == "no_printers"


async def test_cups_config_flow_title_uses_printer_name(hass):  # type: ignore[no-untyped-def]
    """Test that CUPS entry title uses the printer name (not host:port)."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.get_cups_printers",
            return_value=["MyLaserPrinter"],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_printer_available",
            return_value=True,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS},
        )
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_CUPS_SERVER: ""},
        )
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {CONF_PRINTER_NAME: "MyLaserPrinter"},
        )
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
        # Title should be the printer name, not crash with KeyError on CONF_HOST
        assert result5["title"] == "MyLaserPrinter"


async def test_cups_config_flow_printer_unavailable(hass):  # type: ignore[no-untyped-def]
    """Test CUPS config flow when selected printer is unavailable."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_available",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.get_cups_printers",
            return_value=["TestPrinter"],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.cups_steps.is_cups_printer_available",
            return_value=False,
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS},
        )
        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_CUPS_SERVER: ""},
        )
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {CONF_PRINTER_NAME: "TestPrinter"},
        )
        assert result4["type"] == "form"
        assert result4["step_id"] == "cups_printer"
        assert result4["errors"]["base"] == "cannot_connect"


class TestGenerateEntryTitle:
    """Tests for generate_entry_title helper with CUPS connection type."""

    def test_cups_uses_printer_name(self):
        """Test CUPS entry title is the printer name."""
        data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS, CONF_PRINTER_NAME: "OfficePrinter"}
        assert generate_entry_title(data, {}) == "OfficePrinter"

    def test_cups_missing_printer_name_falls_back(self):
        """Test CUPS entry title falls back when printer_name is absent."""
        data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_CUPS}
        assert generate_entry_title(data, {}) == "CUPS Printer"

    def test_network_uses_host_port(self):
        """Test network entry title is host:port."""
        data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK, "host": "192.168.1.1", "port": 9100}
        assert generate_entry_title(data, {}) == "192.168.1.1:9100"

    def test_usb_uses_printer_name_from_user_data(self):
        """Test USB entry title uses _printer_name from user_data."""
        data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB, "vendor_id": 0x04B8, "product_id": 0x0202}
        user_data = {"_printer_name": "Epson TM-T88"}
        assert generate_entry_title(data, user_data) == "Epson TM-T88"

    def test_usb_fallback_hex_ids(self):
        """Test USB entry title falls back to hex VID:PID."""
        data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB, "vendor_id": 0x04B8, "product_id": 0x0202}
        assert generate_entry_title(data, {}) == "USB Printer 04B8:0202"
