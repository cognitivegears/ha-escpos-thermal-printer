"""Tests for CUPS printer adapter."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.escpos_printer.printer import (
    CupsPrinterAdapter,
    CupsPrinterConfig,
    create_printer_adapter,
)


@pytest.fixture
def cups_config():
    """Create a CUPS printer configuration for testing."""
    return CupsPrinterConfig(
        printer_name="TestPrinter",
        cups_server=None,
        timeout=4.0,
        codepage="CP437",
        profile=None,
        line_width=48,
    )


@pytest.fixture
def cups_config_remote():
    """Create a CUPS printer config with remote server."""
    return CupsPrinterConfig(
        printer_name="RemotePrinter",
        cups_server="printserver.local",
        timeout=5.0,
        codepage=None,
        profile=None,
        line_width=48,
    )


@pytest.fixture
def cups_adapter(cups_config):
    """Create a CUPS printer adapter for testing."""
    return CupsPrinterAdapter(cups_config)


class TestCupsPrinterConfig:
    """Tests for CupsPrinterConfig dataclass."""

    def test_default_values(self):
        """Test default values are set correctly."""
        config = CupsPrinterConfig()
        assert config.connection_type == "cups"
        assert config.printer_name == ""
        assert config.cups_server is None
        assert config.timeout == 4.0
        assert config.codepage is None
        assert config.profile is None
        assert config.line_width == 48

    def test_custom_values(self):
        """Test custom values are set correctly."""
        config = CupsPrinterConfig(
            printer_name="MyPrinter",
            cups_server="cups.local:631",
            timeout=5.0,
            codepage="CP932",
            profile="TM-T88V",
            line_width=42,
        )
        assert config.printer_name == "MyPrinter"
        assert config.cups_server == "cups.local:631"
        assert config.timeout == 5.0
        assert config.codepage == "CP932"
        assert config.profile == "TM-T88V"
        assert config.line_width == 42


class TestCupsPrinterAdapter:
    """Tests for CupsPrinterAdapter class."""

    def test_adapter_creation(self, cups_adapter, cups_config):
        """Test adapter is created with correct config."""
        assert cups_adapter._cups_config == cups_config
        assert cups_adapter._keepalive is False

    def test_get_connection_info_local(self, cups_adapter):
        """Test get_connection_info for local CUPS printer."""
        info = cups_adapter.get_connection_info()
        assert info == "CUPS:TestPrinter"

    def test_get_connection_info_remote(self, cups_config_remote):
        """Test get_connection_info for remote CUPS printer."""
        adapter = CupsPrinterAdapter(cups_config_remote)
        info = adapter.get_connection_info()
        assert info == "CUPS:printserver.local/RemotePrinter"

    def test_config_property(self, cups_adapter, cups_config):
        """Test config property returns CUPS config."""
        assert cups_adapter.config == cups_config

    def test_get_status_initial(self, cups_adapter):
        """Test initial status is None."""
        assert cups_adapter.get_status() is None

    def test_get_diagnostics(self, cups_adapter):
        """Test get_diagnostics returns expected structure."""
        diag = cups_adapter.get_diagnostics()
        assert "last_check" in diag
        assert "last_ok" in diag
        assert "last_error" in diag
        assert "last_latency_ms" in diag
        assert "last_error_reason" in diag


class TestCreatePrinterAdapterCups:
    """Tests for create_printer_adapter factory function with CUPS config."""

    def test_creates_cups_adapter_for_cups_config(self, cups_config):
        """Test factory creates CupsPrinterAdapter for CUPS config."""
        adapter = create_printer_adapter(cups_config)
        assert isinstance(adapter, CupsPrinterAdapter)


class TestCupsAdapterConnect:
    """Tests for CUPS adapter _connect method."""

    def test_connect_returns_dummy_printer(self, cups_adapter):
        """Test _connect creates a Dummy printer instance."""
        printer = cups_adapter._connect()
        # The fake Dummy from conftest should have an output property
        assert hasattr(printer, "output")
        assert printer.output == b""

    def test_connect_dummy_printer_buffers_text(self, cups_adapter):
        """Test that the Dummy printer buffers ESC/POS commands."""
        printer = cups_adapter._connect()
        printer.text("Hello")
        assert len(printer.output) > 0


class TestCupsAdapterStatusCheck:
    """Tests for CUPS adapter status checking."""

    @pytest.mark.asyncio
    async def test_status_check_printer_available(self, cups_adapter, hass):
        """Test status check when CUPS printer is available."""
        await cups_adapter._status_check(hass)
        # Default fake cups module reports TestPrinter as available (state=3, idle)
        assert cups_adapter.get_status() is True
        assert cups_adapter._last_error_reason is None

    @pytest.mark.asyncio
    async def test_status_check_printer_not_found(self, cups_adapter, hass):
        """Test status check when CUPS printer is not found."""
        # Use a printer name that doesn't exist in fake module
        cups_adapter._cups_config = CupsPrinterConfig(
            printer_name="NonExistentPrinter",
        )
        await cups_adapter._status_check(hass)
        assert cups_adapter.get_status() is False

    @pytest.mark.asyncio
    async def test_status_check_cups_error(self, cups_adapter, hass):
        """Test status check when CUPS connection fails."""
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._get_cups_connection",
            side_effect=Exception("Connection refused"),
        ):
            await cups_adapter._status_check(hass)
        assert cups_adapter.get_status() is False


class TestCupsAdapterStart:
    """Tests for CUPS adapter start method."""

    @pytest.mark.asyncio
    async def test_start_forces_keepalive_off(self, cups_adapter, hass):
        """Test that CUPS adapter always forces keepalive off."""
        await cups_adapter.start(hass, keepalive=True, status_interval=0)
        assert cups_adapter._keepalive is False

    @pytest.mark.asyncio
    async def test_start_with_status_interval(self, cups_adapter, hass):
        """Test start with status interval schedules checks."""
        await cups_adapter.start(hass, keepalive=False, status_interval=30)
        assert cups_adapter._status_interval == 30
        assert cups_adapter._cancel_status is not None
        # Cleanup
        await cups_adapter.stop()


class TestCupsAdapterPrintOperations:
    """Tests for CUPS adapter print operations."""

    @pytest.mark.asyncio
    async def test_print_text(self, cups_adapter, hass):
        """Test print_text operation submits to CUPS."""
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
            return_value=42,
        ) as mock_submit:
            await cups_adapter.print_text(
                hass,
                text="Hello CUPS Printer",
                align="center",
                bold=True,
                cut="none",
                feed=0,
            )
            mock_submit.assert_called_once()
            args = mock_submit.call_args
            assert args[0][0] == "TestPrinter"  # printer_name
            assert isinstance(args[0][1], bytes)  # data
            assert len(args[0][1]) > 0  # data is non-empty

    @pytest.mark.asyncio
    async def test_print_qr(self, cups_adapter, hass):
        """Test print_qr operation submits to CUPS."""
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
            return_value=43,
        ) as mock_submit:
            await cups_adapter.print_qr(
                hass,
                data="https://example.com",
                size=4,
                cut="none",
                feed=0,
            )
            mock_submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_feed(self, cups_adapter, hass):
        """Test feed operation submits to CUPS."""
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
            return_value=44,
        ) as mock_submit:
            await cups_adapter.feed(hass, lines=3)
            mock_submit.assert_called_once()

    @pytest.mark.asyncio
    async def test_cut(self, cups_adapter, hass):
        """Test cut operation submits to CUPS."""
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
            return_value=45,
        ) as mock_submit:
            await cups_adapter.cut(hass, mode="full")
            mock_submit.assert_called_once()


class TestCupsAdapterReleasePrinter:
    """Tests for the _release_printer override — the core CUPS submit path."""

    @pytest.mark.asyncio
    async def test_release_printer_submits_buffered_data(self, cups_adapter, hass):
        """Test that _release_printer submits buffered Dummy output to CUPS."""
        printer = cups_adapter._connect()
        printer.text("Hello")
        assert len(printer.output) > 0

        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
            return_value=1,
        ) as mock_submit:
            await cups_adapter._release_printer(hass, printer, owned=True)
            mock_submit.assert_called_once_with("TestPrinter", printer.output, None)

    @pytest.mark.asyncio
    async def test_release_printer_empty_output_not_submitted(self, cups_adapter, hass):
        """Test that empty Dummy output does not trigger CUPS submission."""
        printer = cups_adapter._connect()
        assert printer.output == b""

        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
        ) as mock_submit:
            await cups_adapter._release_printer(hass, printer, owned=True)
            mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_printer_not_owned_does_not_submit(self, cups_adapter, hass):
        """Test that owned=False skips submission entirely."""
        printer = cups_adapter._connect()
        printer.text("Hello")

        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
        ) as mock_submit:
            await cups_adapter._release_printer(hass, printer, owned=False)
            mock_submit.assert_not_called()

    @pytest.mark.asyncio
    async def test_release_printer_uses_remote_server(self, cups_config_remote, hass):
        """Test that _release_printer passes the CUPS server to _submit_to_cups."""
        adapter = CupsPrinterAdapter(cups_config_remote)
        printer = adapter._connect()
        printer.text("Remote job")

        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
            return_value=2,
        ) as mock_submit:
            await adapter._release_printer(hass, printer, owned=True)
            mock_submit.assert_called_once_with(
                "RemotePrinter", printer.output, "printserver.local"
            )

    @pytest.mark.asyncio
    async def test_release_printer_without_output_attribute(self, cups_adapter, hass):
        """Test graceful handling when printer lacks output attribute."""
        fake_printer = MagicMock(spec=[])  # no 'output' attribute

        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._submit_to_cups",
        ) as mock_submit:
            await cups_adapter._release_printer(hass, fake_printer, owned=True)
            mock_submit.assert_not_called()


class TestCupsHelperFunctions:
    """Tests for CUPS helper functions."""

    def test_is_cups_available(self):
        """Test is_cups_available with fake module."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            is_cups_available,
        )

        assert is_cups_available() is True

    def test_is_cups_available_with_server(self):
        """Test is_cups_available with server argument."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            is_cups_available,
        )

        assert is_cups_available("localhost") is True

    def test_get_cups_printers(self):
        """Test get_cups_printers returns printer list."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            get_cups_printers,
        )

        printers = get_cups_printers()
        assert "TestPrinter" in printers

    def test_is_cups_printer_available(self):
        """Test is_cups_printer_available checks printer exists."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            is_cups_printer_available,
        )

        assert is_cups_printer_available("TestPrinter") is True
        assert is_cups_printer_available("NonExistent") is False

    def test_get_cups_printer_status_idle(self):
        """Test get_cups_printer_status for idle printer."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            get_cups_printer_status,
        )

        ok, err = get_cups_printer_status("TestPrinter")
        assert ok is True
        assert err is None

    def test_get_cups_printer_status_not_found(self):
        """Test get_cups_printer_status for missing printer."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            get_cups_printer_status,
        )

        ok, err = get_cups_printer_status("NonExistent")
        assert ok is False
        assert err == "Printer not found"

    def test_get_cups_printer_status_stopped(self):
        """Test get_cups_printer_status when printer is stopped (state=5)."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            get_cups_printer_status,
        )

        stopped_printers = {
            "TestPrinter": {
                "printer-state": 5,
                "printer-state-reasons": ["paused"],
            },
        }
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._get_cups_connection",
        ) as mock_conn:
            mock_conn.return_value.getPrinters.return_value = stopped_printers
            ok, err = get_cups_printer_status("TestPrinter")
        assert ok is False
        assert err == "paused"

    def test_get_cups_printer_status_error_reason(self):
        """Test get_cups_printer_status detects error in state_reasons."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            get_cups_printer_status,
        )

        error_printers = {
            "TestPrinter": {
                "printer-state": 3,
                "printer-state-reasons": ["media-empty-error"],
            },
        }
        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._get_cups_connection",
        ) as mock_conn:
            mock_conn.return_value.getPrinters.return_value = error_printers
            ok, err = get_cups_printer_status("TestPrinter")
        assert ok is False
        assert err == "media-empty-error"

    def test_get_cups_printer_status_import_error(self):
        """Test get_cups_printer_status when pycups is not installed."""
        from custom_components.escpos_printer.printer.cups_adapter import (
            get_cups_printer_status,
        )

        with patch(
            "custom_components.escpos_printer.printer.cups_adapter._get_cups_connection",
            side_effect=ImportError("No module named 'cups'"),
        ):
            ok, err = get_cups_printer_status("TestPrinter")
        assert ok is False
        assert err == "pycups library not available"
