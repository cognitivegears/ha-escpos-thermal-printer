"""Tests for USB printer adapter."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.escpos_printer.printer import (
    UsbPrinterAdapter,
    UsbPrinterConfig,
    create_printer_adapter,
)


@pytest.fixture
def usb_config():
    """Create a USB printer configuration for testing."""
    return UsbPrinterConfig(
        vendor_id=0x04B8,
        product_id=0x0202,
        in_ep=0x82,
        out_ep=0x01,
        timeout=4.0,
        codepage="CP437",
        profile=None,
        line_width=48,
    )


@pytest.fixture
def usb_adapter(usb_config):
    """Create a USB printer adapter for testing."""
    return UsbPrinterAdapter(usb_config)


class TestUsbPrinterConfig:
    """Tests for UsbPrinterConfig dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        config = UsbPrinterConfig()
        assert config.connection_type == "usb"
        assert config.vendor_id == 0
        assert config.product_id == 0
        assert config.in_ep == 0x82
        assert config.out_ep == 0x01
        assert config.timeout == 4.0
        assert config.codepage is None
        assert config.profile is None
        assert config.line_width == 48

    def test_custom_values(self):
        """Test custom values are set correctly."""
        config = UsbPrinterConfig(
            vendor_id=0x04B8,
            product_id=0x0202,
            in_ep=0x81,
            out_ep=0x02,
            timeout=5.0,
            codepage="CP932",
            profile="TM-T88V",
            line_width=42,
        )
        assert config.vendor_id == 0x04B8
        assert config.product_id == 0x0202
        assert config.in_ep == 0x81
        assert config.out_ep == 0x02
        assert config.timeout == 5.0
        assert config.codepage == "CP932"
        assert config.profile == "TM-T88V"
        assert config.line_width == 42


class TestUsbPrinterAdapter:
    """Tests for UsbPrinterAdapter class."""

    def test_adapter_creation(self, usb_adapter, usb_config):
        """Test adapter is created with correct config."""
        assert usb_adapter._usb_config == usb_config
        assert usb_adapter._keepalive is False  # USB doesn't support keepalive

    def test_get_connection_info(self, usb_adapter):
        """Test get_connection_info returns correct format."""
        info = usb_adapter.get_connection_info()
        assert info == "USB 04B8:0202"

    def test_config_property(self, usb_adapter, usb_config):
        """Test config property returns USB config."""
        assert usb_adapter.config == usb_config

    def test_get_status_initial(self, usb_adapter):
        """Test initial status is None."""
        assert usb_adapter.get_status() is None

    def test_get_diagnostics(self, usb_adapter):
        """Test get_diagnostics returns expected structure."""
        diag = usb_adapter.get_diagnostics()
        assert "last_check" in diag
        assert "last_ok" in diag
        assert "last_error" in diag
        assert "last_latency_ms" in diag
        assert "last_error_reason" in diag


class TestCreatePrinterAdapter:
    """Tests for create_printer_adapter factory function."""

    def test_creates_usb_adapter_for_usb_config(self, usb_config):
        """Test factory creates UsbPrinterAdapter for USB config."""
        adapter = create_printer_adapter(usb_config)
        assert isinstance(adapter, UsbPrinterAdapter)

    def test_creates_network_adapter_for_network_config(self):
        """Test factory creates NetworkPrinterAdapter for network config."""
        from custom_components.escpos_printer.printer import (
            NetworkPrinterAdapter,
            NetworkPrinterConfig,
        )

        config = NetworkPrinterConfig(host="192.168.1.100", port=9100)
        adapter = create_printer_adapter(config)
        assert isinstance(adapter, NetworkPrinterAdapter)


class TestUsbAdapterStatusCheck:
    """Tests for USB adapter status checking."""

    @pytest.mark.asyncio
    async def test_status_check_device_found(self, usb_adapter, hass):
        """Test status check when USB device is found."""
        mock_device = MagicMock()
        mock_device.idVendor = 0x04B8
        mock_device.idProduct = 0x0202

        with patch("usb.core.find", return_value=mock_device):
            await usb_adapter._status_check(hass)

        assert usb_adapter.get_status() is True
        assert usb_adapter._last_error_reason is None

    @pytest.mark.asyncio
    async def test_status_check_device_not_found(self, usb_adapter, hass):
        """Test status check when USB device is not found."""
        with patch("usb.core.find", return_value=None):
            await usb_adapter._status_check(hass)

        assert usb_adapter.get_status() is False
        assert "not found" in usb_adapter._last_error_reason.lower()


class TestUsbAdapterStart:
    """Tests for USB adapter start method."""

    @pytest.mark.asyncio
    async def test_start_ignores_keepalive(self, usb_adapter, hass):
        """Test that USB adapter ignores keepalive setting."""
        await usb_adapter.start(hass, keepalive=True, status_interval=0)
        # USB should always have keepalive=False
        assert usb_adapter._keepalive is False

    @pytest.mark.asyncio
    async def test_start_with_status_interval(self, usb_adapter, hass):
        """Test start with status interval schedules checks."""
        with patch("usb.core.find", return_value=None):
            await usb_adapter.start(hass, keepalive=False, status_interval=30)

        assert usb_adapter._status_interval == 30
        assert usb_adapter._cancel_status is not None

        # Cleanup
        await usb_adapter.stop()


class TestUsbAdapterPrintOperations:
    """Tests for USB adapter print operations."""

    @pytest.mark.asyncio
    async def test_print_text(self, usb_adapter, hass):
        """Test print_text operation."""
        await usb_adapter.print_text(
            hass,
            text="Hello USB Printer",
            align="center",
            bold=True,
            cut="none",
            feed=0,
        )
        # Should complete without error

    @pytest.mark.asyncio
    async def test_print_qr(self, usb_adapter, hass):
        """Test print_qr operation."""
        await usb_adapter.print_qr(
            hass,
            data="https://example.com",
            size=4,
            cut="none",
            feed=0,
        )
        # Should complete without error

    @pytest.mark.asyncio
    async def test_feed(self, usb_adapter, hass):
        """Test feed operation."""
        await usb_adapter.feed(hass, lines=3)
        # Should complete without error

    @pytest.mark.asyncio
    async def test_cut(self, usb_adapter, hass):
        """Test cut operation."""
        await usb_adapter.cut(hass, mode="full")
        # Should complete without error
