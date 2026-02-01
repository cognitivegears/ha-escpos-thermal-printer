"""Tests for USB printer config flow."""

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from custom_components.escpos_printer.config_flow import EscposConfigFlow
from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONF_IN_EP,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DEFAULT_IN_EP,
    DEFAULT_OUT_EP,
)


@dataclass
class MockUsbServiceInfo:
    """Mock MockUsbServiceInfo for testing."""

    device: str
    vid: str
    pid: str
    serial_number: str | None
    manufacturer: str | None
    description: str | None


@pytest.fixture
def mock_usb_printers():
    """Return mock USB printer discovery results."""
    return [
        {
            "vendor_id": 0x04B8,
            "product_id": 0x0202,
            "manufacturer": "Epson",
            "product": "TM-T88V",
            "serial_number": None,
            "label": "Epson TM-T88V (04B8:0202)",
            "_choice_key": "04B8:0202#0",
        },
        {
            "vendor_id": 0x0416,
            "product_id": 0x5011,
            "manufacturer": "Unknown",
            "product": "Thermal Printer",
            "serial_number": None,
            "label": "Thermal Printer (0416:5011)",
            "_choice_key": "0416:5011#0",
        },
    ]


class TestConnectionTypeStep:
    """Tests for the connection type selection step."""

    @pytest.mark.asyncio
    async def test_step_user_shows_connection_type(self, hass):
        """Test that user step shows connection type selection."""
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user()

        assert result["type"] == "form"
        assert result["step_id"] == "user"
        assert CONF_CONNECTION_TYPE in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_step_user_network_selected(self, hass):
        """Test that selecting network routes to network step."""
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user({CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})

        assert result["type"] == "form"
        assert result["step_id"] == "network"

    @pytest.mark.asyncio
    async def test_step_user_usb_selected(self, hass, mock_usb_printers):
        """Test that selecting USB routes to USB step."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=mock_usb_printers,
        ):
            result = await flow.async_step_user({CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB})

        assert result["type"] == "form"
        assert result["step_id"] == "usb_select"


class TestUsbStep:
    """Tests for the USB configuration step."""

    @pytest.mark.asyncio
    async def test_step_usb_shows_discovered_printers(self, hass, mock_usb_printers):
        """Test that USB step shows discovered printers."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=mock_usb_printers,
        ):
            result = await flow.async_step_usb_select()

        assert result["type"] == "form"
        assert result["step_id"] == "usb_select"
        assert "usb_device" in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_step_usb_no_printers_shows_manual_option(self, hass):
        """Test that USB step shows manual entry as default when no printers found."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[],
        ):
            result = await flow.async_step_usb_select()

        # Still shows the usb_select form but with manual entry as the default
        assert result["type"] == "form"
        assert result["step_id"] == "usb_select"
        # Manual entry should be available in the schema
        assert "usb_device" in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_step_usb_manual_entry_option(self, hass, mock_usb_printers):
        """Test that manual entry option redirects to manual step."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._discovered_printers = mock_usb_printers

        result = await flow.async_step_usb_select({"usb_device": "__manual__"})

        assert result["type"] == "form"
        assert result["step_id"] == "usb_manual"

    @pytest.mark.asyncio
    async def test_step_usb_connection_test_success(self, hass, mock_usb_printers):
        """Test successful USB connection test."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._discovered_printers = mock_usb_printers

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_usb_select({
                "usb_device": "04B8:0202#0",  # New format with index suffix
                "timeout": 4.0,
                "profile": "",
            })

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"

    @pytest.mark.asyncio
    async def test_step_usb_connection_test_failure(self, hass, mock_usb_printers):
        """Test failed USB connection test."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._discovered_printers = mock_usb_printers

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
                return_value=mock_usb_printers,
            ),
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(False, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_usb_select({
                "usb_device": "04B8:0202#0",  # New format with index suffix
                "timeout": 4.0,
                "profile": "",
            })

        assert result["type"] == "form"
        assert result["errors"]["base"] == "cannot_connect_usb"


class TestUsbManualStep:
    """Tests for the manual USB configuration step."""

    @pytest.mark.asyncio
    async def test_step_usb_manual_shows_form(self, hass):
        """Test that USB manual step shows correct form."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        result = await flow.async_step_usb_manual()

        assert result["type"] == "form"
        assert result["step_id"] == "usb_manual"
        assert CONF_VENDOR_ID in result["data_schema"].schema
        assert CONF_PRODUCT_ID in result["data_schema"].schema
        assert CONF_IN_EP in result["data_schema"].schema
        assert CONF_OUT_EP in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_step_usb_manual_invalid_vid_pid(self, hass):
        """Test validation of invalid VID/PID."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        result = await flow.async_step_usb_manual({
            CONF_VENDOR_ID: 0,
            CONF_PRODUCT_ID: 0,
            CONF_IN_EP: DEFAULT_IN_EP,
            CONF_OUT_EP: DEFAULT_OUT_EP,
            "timeout": 4.0,
            "profile": "",
        })

        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_usb_device"

    @pytest.mark.asyncio
    async def test_step_usb_manual_success(self, hass):
        """Test successful manual USB configuration."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_usb_manual({
                CONF_VENDOR_ID: 0x04B8,
                CONF_PRODUCT_ID: 0x0202,
                CONF_IN_EP: DEFAULT_IN_EP,
                CONF_OUT_EP: DEFAULT_OUT_EP,
                "timeout": 4.0,
                "profile": "",
            })

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"


class TestUsbDiscoveryStep:
    """Tests for USB discovery integration."""

    @pytest.mark.asyncio
    async def test_step_usb_discovery_valid(self, hass):
        """Test USB discovery with valid info."""
        flow = EscposConfigFlow()
        flow.hass = hass

        discovery_info = MockUsbServiceInfo(
            device="/dev/usb/001",
            vid="04B8",
            pid="0202",
            serial_number=None,
            manufacturer="Epson",
            description="Epson TM-T88V",
        )

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_usb(discovery_info)

        assert result["type"] == "form"
        assert result["step_id"] == "usb_confirm"

    @pytest.mark.asyncio
    async def test_step_usb_discovery_invalid(self, hass):
        """Test USB discovery with invalid info."""
        flow = EscposConfigFlow()
        flow.hass = hass

        discovery_info = MockUsbServiceInfo(
            device="/dev/usb/001",
            vid="",
            pid="",
            serial_number=None,
            manufacturer=None,
            description=None,
        )

        result = await flow.async_step_usb(discovery_info)

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_discovery_info"


class TestUsbUniqueId:
    """Tests for USB unique ID generation."""

    @pytest.mark.asyncio
    async def test_no_unique_id_without_serial_number(self, hass, mock_usb_printers):
        """Test that no unique ID is set for USB devices without serial numbers."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._discovered_printers = mock_usb_printers

        unique_id_calls = []

        async def capture_unique_id(uid):
            unique_id_calls.append(uid)

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", side_effect=capture_unique_id),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            await flow.async_step_usb_select({
                "usb_device": "04B8:0202#0",  # New format with index suffix
                "timeout": 4.0,
                "profile": "",
            })

        # Without serial number, no unique_id should be set (allows duplicates)
        assert len(unique_id_calls) == 0

    @pytest.mark.asyncio
    async def test_unique_id_with_serial_number(self, hass):
        """Test that USB unique ID includes serial number when available."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        # Mock printer with serial number - use serial in _choice_key
        flow._discovered_printers = [{
            "vendor_id": 0x04B8,
            "product_id": 0x0202,
            "manufacturer": "Epson",
            "product": "TM-T88V",
            "serial_number": "ABC123",
            "label": "Epson TM-T88V (04B8:0202)",
            "_choice_key": "04B8:0202:ABC123",  # Serial in key
        }]

        unique_id_set = None

        async def capture_unique_id(uid):
            nonlocal unique_id_set
            unique_id_set = uid

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", side_effect=capture_unique_id),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            await flow.async_step_usb_select({
                "usb_device": "04B8:0202:ABC123",  # Serial in key
                "timeout": 4.0,
                "profile": "",
            })

        # With serial number, unique_id includes it
        assert unique_id_set == "usb:04b8:0202:ABC123"

    @pytest.mark.asyncio
    async def test_manual_entry_no_unique_id(self, hass):
        """Test that manual USB entry allows duplicates (no unique_id)."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        unique_id_calls = []

        async def capture_unique_id(uid):
            unique_id_calls.append(uid)

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", side_effect=capture_unique_id),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            await flow.async_step_usb_manual({
                CONF_VENDOR_ID: 0x04B8,
                CONF_PRODUCT_ID: 0x0202,
                CONF_IN_EP: DEFAULT_IN_EP,
                CONF_OUT_EP: DEFAULT_OUT_EP,
                "timeout": 4.0,
                "profile": "",
            })

        # Manual entry should not set unique_id
        assert len(unique_id_calls) == 0


class TestUsbYamlImport:
    """Tests for USB YAML import functionality."""

    @pytest.mark.asyncio
    async def test_import_usb_valid(self, hass):
        """Test importing USB printer from YAML."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: 0x04B8,
                CONF_PRODUCT_ID: 0x0202,
            })

        assert result["type"] == "create_entry"
        assert result["title"] == "USB Printer 04B8:0202"
        assert result["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_USB
        assert result["data"][CONF_VENDOR_ID] == 0x04B8
        assert result["data"][CONF_PRODUCT_ID] == 0x0202
        assert result["data"][CONF_IN_EP] == DEFAULT_IN_EP
        assert result["data"][CONF_OUT_EP] == DEFAULT_OUT_EP

    @pytest.mark.asyncio
    async def test_import_usb_with_custom_endpoints(self, hass):
        """Test importing USB printer from YAML with custom endpoints."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: 0x0519,
                CONF_PRODUCT_ID: 0x0001,
                CONF_IN_EP: 0x81,
                CONF_OUT_EP: 0x02,
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_IN_EP] == 0x81
        assert result["data"][CONF_OUT_EP] == 0x02

    @pytest.mark.asyncio
    async def test_import_usb_hex_string_with_prefix(self, hass):
        """Test importing USB printer with hex string VID/PID (0x prefix)."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "0x04B8",
                CONF_PRODUCT_ID: "0x0202",
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 0x04B8
        assert result["data"][CONF_PRODUCT_ID] == 0x0202

    @pytest.mark.asyncio
    async def test_import_usb_decimal_string(self, hass):
        """Test importing USB printer with decimal string VID/PID."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "1208",  # 0x04B8 in decimal
                CONF_PRODUCT_ID: "514",   # 0x0202 in decimal
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 1208
        assert result["data"][CONF_PRODUCT_ID] == 514

    @pytest.mark.asyncio
    async def test_import_usb_invalid_string(self, hass):
        """Test importing USB printer with invalid string VID/PID aborts."""
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_import({
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_VENDOR_ID: "not_a_number",
            CONF_PRODUCT_ID: "0x0202",
        })

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_usb_device"

    @pytest.mark.asyncio
    async def test_import_usb_missing_vid(self, hass):
        """Test importing USB printer without vendor ID aborts."""
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_import({
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_PRODUCT_ID: 0x0202,
        })

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_usb_device"

    @pytest.mark.asyncio
    async def test_import_usb_missing_pid(self, hass):
        """Test importing USB printer without product ID aborts."""
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_import({
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_VENDOR_ID: 0x04B8,
        })

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_usb_device"

    @pytest.mark.asyncio
    async def test_import_network_still_works(self, hass):
        """Test that network YAML import still routes correctly."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch(
                "custom_components.escpos_printer._config_flow.network_steps._can_connect",
                return_value=True,
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                "host": "192.168.1.100",
                "port": 9100,
            })

        # Should route to network step and show codepage form on success
        assert result["type"] == "form"
        assert result["step_id"] == "codepage"


class TestMultipleIdenticalPrinters:
    """Tests for handling multiple USB printers with same VID/PID."""

    @pytest.mark.asyncio
    async def test_multiple_printers_same_vid_pid_without_serial(self, hass):
        """Test that multiple printers with same VID/PID are individually selectable."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        # Two identical printers without serial numbers
        mock_printers = [
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": None,
                "label": "Epson TM-T88V (04B8:0202)",
            },
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": None,
                "label": "Epson TM-T88V (04B8:0202)",
            },
        ]

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=mock_printers,
        ):
            result = await flow.async_step_usb_select()

        # Both printers should appear in choices with unique keys
        schema = result["data_schema"].schema
        usb_device_schema = schema.get("usb_device")
        choices = usb_device_schema.container

        # Should have 4 entries: two printers + browse all + manual entry
        assert len(choices) == 4
        assert "04B8:0202#0" in choices
        assert "04B8:0202#1" in choices
        assert "__browse_all__" in choices
        assert "__manual__" in choices

    @pytest.mark.asyncio
    async def test_multiple_printers_same_vid_pid_with_serial(self, hass):
        """Test that multiple printers with serial numbers use serial in key."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        # Two identical printers with different serial numbers
        mock_printers = [
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": "SERIAL001",
                "label": "Epson TM-T88V (04B8:0202)",
            },
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": "SERIAL002",
                "label": "Epson TM-T88V (04B8:0202)",
            },
        ]

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=mock_printers,
        ):
            result = await flow.async_step_usb_select()

        # Both printers should appear with serial-based keys
        schema = result["data_schema"].schema
        usb_device_schema = schema.get("usb_device")
        choices = usb_device_schema.container

        # Should have 4 entries: two printers + browse all + manual entry
        assert len(choices) == 4
        assert "04B8:0202:SERIAL001" in choices
        assert "04B8:0202:SERIAL002" in choices
        assert "__browse_all__" in choices
        assert "__manual__" in choices

    @pytest.mark.asyncio
    async def test_select_second_printer_with_same_vid_pid(self, hass):
        """Test selecting the second printer when multiple have same VID/PID."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        # Setup discovered printers with _choice_key already set
        flow._discovered_printers = [
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V #1",
                "serial_number": None,
                "label": "Epson TM-T88V #1 (04B8:0202)",
                "_choice_key": "04B8:0202#0",
            },
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V #2",
                "serial_number": None,
                "label": "Epson TM-T88V #2 (04B8:0202)",
                "_choice_key": "04B8:0202#1",
            },
        ]

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            # Select the SECOND printer using index suffix
            result = await flow.async_step_usb_select({
                "usb_device": "04B8:0202#1",
                "timeout": 4.0,
                "profile": "",
            })

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"

        # Verify the correct printer name was captured
        assert flow._user_data.get("_printer_name") == "Epson TM-T88V #2"

    @pytest.mark.asyncio
    async def test_mixed_serial_and_no_serial_printers(self, hass):
        """Test handling mix of printers with and without serial numbers."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        # Mix of printers: some with serial, some without
        mock_printers = [
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": "ABC123",
                "label": "Epson TM-T88V (04B8:0202)",
            },
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": None,
                "label": "Epson TM-T88V (04B8:0202)",
            },
            {
                "vendor_id": 0x0416,
                "product_id": 0x5011,
                "manufacturer": "Generic",
                "product": "Thermal",
                "serial_number": None,
                "label": "Generic Thermal (0416:5011)",
            },
        ]

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=mock_printers,
        ):
            result = await flow.async_step_usb_select()

        schema = result["data_schema"].schema
        usb_device_schema = schema.get("usb_device")
        choices = usb_device_schema.container

        # Should have 5 entries: 3 printers + browse all + manual entry
        assert len(choices) == 5
        # Printer with serial uses serial in key
        assert "04B8:0202:ABC123" in choices
        # Printer without serial uses index
        assert "04B8:0202#0" in choices
        # Different VID:PID printer uses index
        assert "0416:5011#0" in choices
        assert "__browse_all__" in choices
        assert "__manual__" in choices


class TestBrowseAllUsbDevices:
    """Tests for browsing all USB devices functionality."""

    @pytest.mark.asyncio
    async def test_browse_all_option_redirects_to_all_devices_step(self, hass, mock_usb_printers):
        """Test that browse all option redirects to usb_all_devices step."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._discovered_printers = mock_usb_printers

        # Mock all USB devices discovery
        mock_all_devices = [
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": None,
                "is_known_printer": True,
                "label": "Epson TM-T88V (04B8:0202)",
            },
            {
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "manufacturer": "Unknown",
                "product": "USB Device",
                "serial_number": None,
                "is_known_printer": False,
                "label": "Unknown USB Device (1234:5678)",
            },
        ]

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_all_usb_devices",
            return_value=mock_all_devices,
        ):
            result = await flow.async_step_usb_select({"usb_device": "__browse_all__"})

        assert result["type"] == "form"
        assert result["step_id"] == "usb_all_devices"

    @pytest.mark.asyncio
    async def test_all_devices_step_shows_all_usb_devices(self, hass):
        """Test that usb_all_devices step shows all connected USB devices."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        # Mock all USB devices (including non-printers)
        mock_all_devices = [
            {
                "vendor_id": 0x04B8,
                "product_id": 0x0202,
                "manufacturer": "Epson",
                "product": "TM-T88V",
                "serial_number": None,
                "is_known_printer": True,
                "label": "Epson TM-T88V (04B8:0202)",
            },
            {
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "manufacturer": "Generic",
                "product": "Unknown Device",
                "serial_number": None,
                "is_known_printer": False,
                "label": "Generic Unknown Device (1234:5678)",
            },
            {
                "vendor_id": 0xABCD,
                "product_id": 0xEF01,
                "manufacturer": "Other",
                "product": "Keyboard",
                "serial_number": None,
                "is_known_printer": False,
                "label": "Other Keyboard (ABCD:EF01)",
            },
        ]

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_all_usb_devices",
            return_value=mock_all_devices,
        ):
            result = await flow.async_step_usb_all_devices()

        assert result["type"] == "form"
        assert result["step_id"] == "usb_all_devices"

        # Check that all devices are in choices
        schema = result["data_schema"].schema
        usb_device_schema = schema.get("usb_device")
        choices = usb_device_schema.container

        # Should have 4 entries: 3 devices + manual entry (no browse_all in this step)
        assert len(choices) == 4
        assert "04B8:0202#0" in choices
        assert "1234:5678#0" in choices
        assert "ABCD:EF01#0" in choices
        assert "__manual__" in choices
        # Should NOT have browse_all option in this step
        assert "__browse_all__" not in choices

    @pytest.mark.asyncio
    async def test_all_devices_step_includes_endpoint_config(self, hass):
        """Test that usb_all_devices step includes endpoint configuration."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        mock_all_devices = [
            {
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "manufacturer": "Generic",
                "product": "Device",
                "serial_number": None,
                "is_known_printer": False,
                "label": "Generic Device (1234:5678)",
            },
        ]

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_all_usb_devices",
            return_value=mock_all_devices,
        ):
            result = await flow.async_step_usb_all_devices()

        # Should include endpoint configuration since devices may not be standard printers
        schema = result["data_schema"].schema
        assert CONF_IN_EP in schema
        assert CONF_OUT_EP in schema

    @pytest.mark.asyncio
    async def test_all_devices_step_selection_success(self, hass):
        """Test successful device selection from all devices step."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._all_usb_devices = [
            {
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "manufacturer": "Generic",
                "product": "Thermal Printer",
                "serial_number": None,
                "is_known_printer": False,
                "label": "Generic Thermal Printer (1234:5678)",
                "_choice_key": "1234:5678#0",
            },
        ]

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_usb_all_devices({
                "usb_device": "1234:5678#0",
                CONF_IN_EP: DEFAULT_IN_EP,
                CONF_OUT_EP: DEFAULT_OUT_EP,
                "timeout": 4.0,
                "profile": "",
            })

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"
        assert flow._user_data["_printer_name"] == "Generic Thermal Printer"

    @pytest.mark.asyncio
    async def test_all_devices_step_manual_entry_redirect(self, hass):
        """Test that manual entry option redirects from all devices step."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._all_usb_devices = []

        result = await flow.async_step_usb_all_devices({"usb_device": "__manual__"})

        assert result["type"] == "form"
        assert result["step_id"] == "usb_manual"

    @pytest.mark.asyncio
    async def test_all_devices_step_no_devices_redirects_to_manual(self, hass):
        """Test that empty device list redirects to manual entry."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}

        with patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_all_usb_devices",
            return_value=[],
        ):
            result = await flow.async_step_usb_all_devices()

        assert result["type"] == "form"
        assert result["step_id"] == "usb_manual"

    @pytest.mark.asyncio
    async def test_all_devices_step_connection_failure(self, hass):
        """Test connection failure handling in all devices step."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
        flow._all_usb_devices = [
            {
                "vendor_id": 0x1234,
                "product_id": 0x5678,
                "manufacturer": "Generic",
                "product": "Device",
                "serial_number": None,
                "is_known_printer": False,
                "label": "Generic Device (1234:5678)",
                "_choice_key": "1234:5678#0",
            },
        ]

        mock_all_devices = flow._all_usb_devices.copy()

        with (
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._discover_all_usb_devices",
                return_value=mock_all_devices,
            ),
            patch(
                "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
                return_value=(False, "permission_denied", 13),
            ),
        ):
            result = await flow.async_step_usb_all_devices({
                "usb_device": "1234:5678#0",
                CONF_IN_EP: DEFAULT_IN_EP,
                CONF_OUT_EP: DEFAULT_OUT_EP,
                "timeout": 4.0,
                "profile": "",
            })

        assert result["type"] == "form"
        assert result["errors"]["base"] == "usb_permission_denied"


class TestParseVidPid:
    """Tests for the _parse_vid_pid helper function."""

    def test_parse_integer(self):
        """Test parsing integer values."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        assert _parse_vid_pid(0x04B8) == 0x04B8
        assert _parse_vid_pid(1208) == 1208
        assert _parse_vid_pid(0) == 0

    def test_parse_hex_with_prefix(self):
        """Test parsing hex strings with 0x prefix."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        assert _parse_vid_pid("0x04B8") == 0x04B8
        assert _parse_vid_pid("0X04B8") == 0x04B8
        assert _parse_vid_pid("0x04b8") == 0x04B8
        assert _parse_vid_pid("0x0202") == 0x0202
        assert _parse_vid_pid("0xFFFF") == 0xFFFF

    def test_parse_hex_without_prefix(self):
        """Test parsing hex strings without prefix (containing a-f)."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        assert _parse_vid_pid("04b8") == 0x04B8
        assert _parse_vid_pid("04B8") == 0x04B8
        assert _parse_vid_pid("ABCD") == 0xABCD
        assert _parse_vid_pid("abcd") == 0xABCD
        assert _parse_vid_pid("0a0b") == 0x0A0B

    def test_parse_decimal_string(self):
        """Test parsing decimal strings (pure digits)."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        assert _parse_vid_pid("1208") == 1208
        assert _parse_vid_pid("514") == 514
        assert _parse_vid_pid("0") == 0
        assert _parse_vid_pid("65535") == 65535

    def test_parse_with_whitespace(self):
        """Test parsing strings with leading/trailing whitespace."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        assert _parse_vid_pid("  1208  ") == 1208
        assert _parse_vid_pid(" 0x04B8 ") == 0x04B8
        assert _parse_vid_pid("\t04b8\n") == 0x04B8

    def test_parse_invalid_string(self):
        """Test that invalid strings raise ValueError."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        with pytest.raises(ValueError):
            _parse_vid_pid("not_a_number")

        with pytest.raises(ValueError):
            _parse_vid_pid("xyz123")

        with pytest.raises(ValueError):
            _parse_vid_pid("")

        with pytest.raises(ValueError):
            _parse_vid_pid("   ")

    def test_parse_invalid_type(self):
        """Test that invalid types raise TypeError."""
        from custom_components.escpos_printer.config_flow import _parse_vid_pid

        with pytest.raises(TypeError):
            _parse_vid_pid(None)  # type: ignore[arg-type]

        with pytest.raises(TypeError):
            _parse_vid_pid([1, 2, 3])  # type: ignore[arg-type]


class TestUsbYamlImportEdgeCases:
    """Additional edge case tests for USB YAML import VID/PID parsing."""

    @pytest.mark.asyncio
    async def test_import_usb_hex_string_without_prefix(self, hass):
        """Test importing USB printer with hex string VID/PID (no 0x prefix)."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "04b8",  # Hex without prefix
                CONF_PRODUCT_ID: "0202",  # This will be parsed as decimal since no hex letters
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 0x04B8
        # "0202" has no hex letters, so parsed as decimal 202
        assert result["data"][CONF_PRODUCT_ID] == 202

    @pytest.mark.asyncio
    async def test_import_usb_uppercase_hex_letters(self, hass):
        """Test importing USB printer with uppercase hex letters."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "ABCD",
                CONF_PRODUCT_ID: "EF01",
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 0xABCD
        assert result["data"][CONF_PRODUCT_ID] == 0xEF01

    @pytest.mark.asyncio
    async def test_import_usb_mixed_formats(self, hass):
        """Test importing USB printer with mixed VID/PID formats."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "0x04B8",  # Hex with prefix
                CONF_PRODUCT_ID: "514",     # Decimal
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 0x04B8
        assert result["data"][CONF_PRODUCT_ID] == 514

    @pytest.mark.asyncio
    async def test_import_usb_whitespace_in_strings(self, hass):
        """Test importing USB printer with whitespace in VID/PID strings."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "  0x04B8  ",
                CONF_PRODUCT_ID: " 514 ",
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 0x04B8
        assert result["data"][CONF_PRODUCT_ID] == 514

    @pytest.mark.asyncio
    async def test_import_usb_empty_string_aborts(self, hass):
        """Test that empty string VID/PID aborts."""
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_import({
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_VENDOR_ID: "",
            CONF_PRODUCT_ID: "0x0202",
        })

        assert result["type"] == "abort"
        assert result["reason"] == "invalid_usb_device"

    @pytest.mark.asyncio
    async def test_import_usb_lowercase_0x_prefix(self, hass):
        """Test importing USB printer with lowercase 0x prefix."""
        flow = EscposConfigFlow()
        flow.hass = hass

        with (
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_import({
                CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
                CONF_VENDOR_ID: "0x04b8",
                CONF_PRODUCT_ID: "0x0202",
            })

        assert result["type"] == "create_entry"
        assert result["data"][CONF_VENDOR_ID] == 0x04B8
        assert result["data"][CONF_PRODUCT_ID] == 0x0202
