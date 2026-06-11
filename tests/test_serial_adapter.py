"""Tests for serial printer adapter."""

from unittest.mock import MagicMock, call, patch

import pytest

from custom_components.escpos_printer.printer import (
    BluetoothPrinterConfig,
    NetworkPrinterConfig,
    SerialPrinterAdapter,
    SerialPrinterConfig,
    UsbPrinterConfig,
    create_printer_adapter,
)
from custom_components.escpos_printer.printer.serial_adapter import _is_url


class TestSerialPrinterConfig:
    """Tests for SerialPrinterConfig dataclass."""

    def test_default_values(self):
        config = SerialPrinterConfig()
        assert config.connection_type == "serial"
        assert config.serial_port == ""
        assert config.baudrate == 9600
        assert config.timeout == 4.0
        assert config.codepage is None
        assert config.profile is None
        assert config.line_width == 48

    def test_custom_values(self):
        config = SerialPrinterConfig(
            serial_port="/dev/ttyUSB0",
            baudrate=115200,
            timeout=6.0,
            codepage="CP437",
            profile="TM-T88V",
            line_width=42,
        )
        assert config.serial_port == "/dev/ttyUSB0"
        assert config.baudrate == 115200
        assert config.timeout == 6.0
        assert config.codepage == "CP437"
        assert config.profile == "TM-T88V"
        assert config.line_width == 42

    def test_url_based_port(self):
        config = SerialPrinterConfig(serial_port="esphome://192.168.1.100:6638")
        assert config.serial_port == "esphome://192.168.1.100:6638"


class TestIsUrl:
    """Tests for _is_url helper."""

    def test_device_path_is_not_url(self):
        assert _is_url("/dev/ttyUSB0") is False

    def test_windows_com_port_is_not_url(self):
        assert _is_url("COM3") is False

    def test_esphome_url(self):
        assert _is_url("esphome://192.168.1.100:6638") is True

    def test_rfc2217_url(self):
        assert _is_url("rfc2217://host:2217") is True

    def test_socket_url(self):
        assert _is_url("socket://host:9100") is True


@pytest.fixture
def serial_config():
    """Return a serial printer configuration for testing."""
    return SerialPrinterConfig(
        serial_port="/dev/ttyUSB0",
        baudrate=9600,
        timeout=4.0,
        codepage="CP437",
        profile=None,
        line_width=48,
    )


@pytest.fixture
def serial_adapter(serial_config):
    """Return a serial printer adapter for testing."""
    return SerialPrinterAdapter(serial_config)


@pytest.fixture
def url_config():
    """Return a URL-based serial printer configuration for testing."""
    return SerialPrinterConfig(
        serial_port="esphome://192.168.1.100:6638",
        baudrate=9600,
        timeout=4.0,
    )


@pytest.fixture
def url_adapter(url_config):
    """Return a URL-based serial printer adapter for testing."""
    return SerialPrinterAdapter(url_config)


class TestSerialPrinterAdapter:
    """Tests for SerialPrinterAdapter class."""

    def test_adapter_creation(self, serial_adapter, serial_config):
        assert serial_adapter._serial_config == serial_config
        assert serial_adapter._keepalive is False

    def test_default_chunk_delay(self, serial_adapter):
        assert serial_adapter.default_chunk_delay_ms == 0

    def test_get_connection_info_path(self, serial_adapter):
        info = serial_adapter.get_connection_info()
        assert "/dev/ttyUSB0" in info
        assert "9600" in info

    def test_get_connection_info_url(self, url_adapter):
        info = url_adapter.get_connection_info()
        assert "192.168.1.100" in info
        # URL-based connections should not append baudrate
        assert "9600" not in info

    def test_config_property(self, serial_adapter, serial_config):
        assert serial_adapter.config == serial_config

    def test_get_status_initial(self, serial_adapter):
        assert serial_adapter.get_status() is None

    def test_get_diagnostics(self, serial_adapter):
        diag = serial_adapter.get_diagnostics()
        assert "last_check" in diag
        assert "last_ok" in diag
        assert "last_error" in diag
        assert "last_latency_ms" in diag
        assert "last_error_reason" in diag

    def test_connect_calls_transport(self, serial_adapter):
        mock_transport = MagicMock()
        mock_escpos = MagicMock()
        with (
            patch(
                "custom_components.escpos_printer.printer.serial_adapter.serial_transport"
                ".open_serial_transport",
                return_value=mock_transport,
            ) as mock_open,
            patch(
                "custom_components.escpos_printer.printer.serial_adapter.make_serial_escpos",
                return_value=mock_escpos,
            ) as mock_make,
        ):
            result = serial_adapter._connect()

        mock_open.assert_called_once_with(
            "/dev/ttyUSB0",
            9600,
            pytest.approx(4.0, abs=0.01),
            write_chunk_size=0,
            write_chunk_delay_ms=0,
        )
        mock_make.assert_called_once_with(mock_transport, serial_adapter._get_profile_obj())
        assert result is mock_escpos

    def test_connect_retries_on_ebusy(self, serial_adapter):
        import errno as _errno

        call_count = 0

        def failing_then_ok(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                exc = OSError("busy")
                exc.errno = _errno.EBUSY
                raise exc
            return MagicMock()

        with (
            patch(
                "custom_components.escpos_printer.printer.serial_adapter.serial_transport"
                ".open_serial_transport",
                side_effect=failing_then_ok,
            ),
            patch(
                "custom_components.escpos_printer.printer.serial_adapter.make_serial_escpos",
                return_value=MagicMock(),
            ),
            patch("time.sleep"),
        ):
            result = serial_adapter._connect()

        assert call_count == 2
        assert result is not None

    def test_connect_raises_after_max_retries(self, serial_adapter):
        import errno as _errno

        exc = OSError("busy")
        exc.errno = _errno.EBUSY

        with (
            patch(
                "custom_components.escpos_printer.printer.serial_adapter.serial_transport"
                ".open_serial_transport",
                side_effect=exc,
            ),
            patch("time.sleep"),
        ):
            with pytest.raises(OSError):
                serial_adapter._connect()

    def test_connect_does_not_retry_permission_error(self, serial_adapter):
        import errno as _errno

        call_count = 0

        def always_fails(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            exc = OSError("permission denied")
            exc.errno = _errno.EACCES
            raise exc

        with (
            patch(
                "custom_components.escpos_printer.printer.serial_adapter.serial_transport"
                ".open_serial_transport",
                side_effect=always_fails,
            ),
            patch("time.sleep"),
        ):
            with pytest.raises(OSError):
                serial_adapter._connect()

        assert call_count == 1  # No retries for non-retryable error


class TestSerialStatusCheck:
    """Tests for serial status check logic."""

    @pytest.mark.asyncio
    async def test_status_check_path_device_exists(self, hass, serial_adapter):
        import stat

        mock_stat = MagicMock()
        mock_stat.st_mode = stat.S_IFCHR | 0o666

        with patch("os.stat", return_value=mock_stat):
            await serial_adapter._status_check(hass)

        assert serial_adapter.get_status() is True

    @pytest.mark.asyncio
    async def test_status_check_path_not_found(self, hass, serial_adapter):
        exc = OSError("no such file")
        exc.errno = 2

        with patch("os.stat", side_effect=exc):
            await serial_adapter._status_check(hass)

        assert serial_adapter.get_status() is False

    @pytest.mark.asyncio
    async def test_status_check_path_not_char_device(self, hass, serial_adapter):
        import stat

        mock_stat = MagicMock()
        mock_stat.st_mode = stat.S_IFREG | 0o666  # regular file, not char device

        with patch("os.stat", return_value=mock_stat):
            await serial_adapter._status_check(hass)

        assert serial_adapter.get_status() is False

    @pytest.mark.asyncio
    async def test_status_check_url_success(self, hass, url_adapter):
        mock_transport = MagicMock()
        with patch(
            "custom_components.escpos_printer.printer.serial_adapter.serial_transport"
            ".open_serial_transport",
            return_value=mock_transport,
        ):
            await url_adapter._status_check(hass)

        assert url_adapter.get_status() is True
        mock_transport.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_status_check_url_failure(self, hass, url_adapter):
        exc = OSError("connection refused")
        exc.errno = 111

        with patch(
            "custom_components.escpos_printer.printer.serial_adapter.serial_transport"
            ".open_serial_transport",
            side_effect=exc,
        ):
            await url_adapter._status_check(hass)

        assert url_adapter.get_status() is False

    @pytest.mark.asyncio
    async def test_status_check_skipped_when_locked(self, hass, serial_adapter):
        async with serial_adapter._lock:
            with patch("os.stat") as mock_stat:
                await serial_adapter._status_check(hass)
                mock_stat.assert_not_called()

        # Status should remain None (never set)
        assert serial_adapter.get_status() is None


class TestCreatePrinterAdapterSerial:
    """Tests for create_printer_adapter factory with serial config."""

    def test_creates_serial_adapter_for_serial_config(self, serial_config):
        adapter = create_printer_adapter(serial_config)
        assert isinstance(adapter, SerialPrinterAdapter)

    def test_network_config_still_makes_network_adapter(self):
        from custom_components.escpos_printer.printer import NetworkPrinterAdapter

        config = NetworkPrinterConfig(host="192.168.1.100", port=9100)
        adapter = create_printer_adapter(config)
        assert isinstance(adapter, NetworkPrinterAdapter)

    def test_usb_config_still_makes_usb_adapter(self):
        from custom_components.escpos_printer.printer import UsbPrinterAdapter

        config = UsbPrinterConfig(vendor_id=0x04B8, product_id=0x0202)
        adapter = create_printer_adapter(config)
        assert isinstance(adapter, UsbPrinterAdapter)

    def test_bluetooth_config_still_makes_bt_adapter(self):
        from custom_components.escpos_printer.printer import BluetoothPrinterAdapter

        config = BluetoothPrinterConfig(mac="AA:BB:CC:DD:EE:FF")
        adapter = create_printer_adapter(config)
        assert isinstance(adapter, BluetoothPrinterAdapter)


class TestSerialTransportImpl:
    """Tests for _SerialTransportImpl write coalescing and flush-on-close."""

    def _make_transport(self, write_chunk_size=0, write_chunk_delay_s=0.0):
        from custom_components.escpos_printer.printer.serial_transport import (
            _SerialTransportImpl,
        )

        port = MagicMock()
        transport = _SerialTransportImpl(
            port,
            write_chunk_size=write_chunk_size,
            write_chunk_delay_s=write_chunk_delay_s,
        )
        return transport, port

    def test_write_buffers_without_touching_port(self):
        transport, port = self._make_transport()
        transport.write(b"hello")
        transport.write(b" world")
        port.write.assert_not_called()

    def test_close_flushes_coalesced_buffer(self):
        transport, port = self._make_transport()
        transport.write(b"hello")
        transport.write(b" world")
        transport.close()
        port.write.assert_called_once_with(b"hello world")

    def test_close_with_empty_buffer_does_not_write(self):
        transport, port = self._make_transport()
        transport.close()
        port.write.assert_not_called()

    def test_flush_splits_into_chunks(self):
        transport, port = self._make_transport(write_chunk_size=4)
        transport.write(b"0123456789")  # 10 bytes → chunks of 4, 4, 2
        transport.close()
        assert port.write.call_args_list == [
            call(b"0123"),
            call(b"4567"),
            call(b"89"),
        ]

    def test_flush_with_chunk_delay(self):
        transport, port = self._make_transport(write_chunk_size=4, write_chunk_delay_s=0.001)
        transport.write(b"01234567")  # 8 bytes → 2 chunks of 4
        with patch("custom_components.escpos_printer.printer.serial_transport.time.sleep") as mock_sleep:
            transport.close()
        assert port.write.call_count == 2
        mock_sleep.assert_called_once_with(0.001)

    def test_close_suppresses_flush_error(self):
        transport, port = self._make_transport()
        port.write.side_effect = OSError("port gone")
        transport.write(b"data")
        transport.close()  # must not raise

    def test_close_closes_port_even_after_flush_error(self):
        transport, port = self._make_transport()
        port.write.side_effect = OSError("port gone")
        transport.write(b"data")
        transport.close()
        port.close.assert_called_once()
