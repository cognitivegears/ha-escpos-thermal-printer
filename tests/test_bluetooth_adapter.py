"""Tests for Bluetooth Classic / RFCOMM printer adapter."""

from unittest.mock import patch

import pytest

from custom_components.escpos_printer.printer import (
    BluetoothPrinterAdapter,
    BluetoothPrinterConfig,
    NetworkPrinterAdapter,
    NetworkPrinterConfig,
    bluetooth_transport,
    create_printer_adapter,
)


@pytest.fixture
def bt_config():
    """Return a Bluetooth printer configuration for testing."""
    return BluetoothPrinterConfig(
        mac="AA:BB:CC:DD:EE:FF",
        rfcomm_channel=1,
        timeout=4.0,
        codepage="CP437",
        profile=None,
        line_width=48,
    )


@pytest.fixture
def bt_adapter(bt_config):
    """Return a Bluetooth printer adapter for testing."""
    return BluetoothPrinterAdapter(bt_config)


class TestBluetoothPrinterConfig:
    """Tests for BluetoothPrinterConfig dataclass."""

    def test_default_values(self):
        config = BluetoothPrinterConfig()
        assert config.connection_type == "bluetooth"
        assert config.mac == ""
        assert config.rfcomm_channel == 1
        assert config.timeout == 4.0
        assert config.codepage is None
        assert config.profile is None
        assert config.line_width == 48

    def test_custom_values(self):
        config = BluetoothPrinterConfig(
            mac="11:22:33:44:55:66",
            rfcomm_channel=3,
            timeout=6.0,
            codepage="CP932",
            profile="TM-T88V",
            line_width=42,
        )
        assert config.mac == "11:22:33:44:55:66"
        assert config.rfcomm_channel == 3
        assert config.timeout == 6.0
        assert config.codepage == "CP932"
        assert config.profile == "TM-T88V"
        assert config.line_width == 42


class TestBluetoothPrinterAdapter:
    """Tests for BluetoothPrinterAdapter class."""

    def test_adapter_creation(self, bt_adapter, bt_config):
        assert bt_adapter._bt_config == bt_config
        # Bluetooth printers don't support keepalive (single connection per op).
        assert bt_adapter._keepalive is False

    def test_get_connection_info(self, bt_adapter):
        assert bt_adapter.get_connection_info() == "BT AA:BB:CC:DD:EE:FF ch=1"

    def test_config_property(self, bt_adapter, bt_config):
        assert bt_adapter.config == bt_config

    def test_get_status_initial(self, bt_adapter):
        assert bt_adapter.get_status() is None

    def test_get_diagnostics(self, bt_adapter):
        diag = bt_adapter.get_diagnostics()
        assert "last_check" in diag
        assert "last_ok" in diag
        assert "last_error" in diag
        assert "last_latency_ms" in diag
        assert "last_error_reason" in diag


class TestCreatePrinterAdapter:
    """Tests for create_printer_adapter factory."""

    def test_creates_bt_adapter_for_bt_config(self, bt_config):
        adapter = create_printer_adapter(bt_config)
        assert isinstance(adapter, BluetoothPrinterAdapter)

    def test_network_config_still_makes_network_adapter(self):
        config = NetworkPrinterConfig(host="192.168.1.100", port=9100)
        assert isinstance(create_printer_adapter(config), NetworkPrinterAdapter)


class TestBluetoothAdapterStatusCheck:
    """Tests for Bluetooth adapter status checking."""

    @pytest.mark.asyncio
    async def test_status_check_reachable(self, bt_adapter, hass):
        # The default fake_bluetooth_module fixture stubs open_rfcomm_transport
        # to succeed; status check should mark the printer reachable.
        await bt_adapter._status_check(hass)
        assert bt_adapter.get_status() is True
        assert bt_adapter._last_error_reason is None

    @pytest.mark.asyncio
    async def test_status_check_unreachable(self, bt_adapter, hass):
        def _raise_unreachable(_mac, _ch, _to):
            raise OSError(113, "No route to host")  # EHOSTUNREACH

        with patch.object(
            bluetooth_transport, "open_rfcomm_transport", side_effect=_raise_unreachable
        ):
            await bt_adapter._status_check(hass)
        assert bt_adapter.get_status() is False
        assert bt_adapter._last_error_reason
        assert bt_adapter._last_error_errno == 113

    @pytest.mark.asyncio
    async def test_status_check_unavailable_platform(self, bt_adapter, hass):
        def _raise_unavailable(_mac, _ch, _to):
            raise OSError(
                "AF_BLUETOOTH/BTPROTO_RFCOMM not available on this platform."
            )

        with patch.object(
            bluetooth_transport, "open_rfcomm_transport", side_effect=_raise_unavailable
        ):
            await bt_adapter._status_check(hass)
        assert bt_adapter.get_status() is False


class TestBluetoothAdapterStatusLockRace:
    """Regression test for the status-vs-print race (security finding S-H2)."""

    @pytest.mark.asyncio
    async def test_status_check_skips_when_lock_held(self, bt_adapter, hass):
        """Status check must not race for the printer's only RFCOMM slot."""
        # Snapshot pre-tick state — should be untouched after the no-op probe.
        prior_check = bt_adapter._last_check
        prior_status = bt_adapter.get_status()

        async with bt_adapter._lock:
            await bt_adapter._status_check(hass)

        assert bt_adapter._last_check is prior_check
        assert bt_adapter.get_status() is prior_status

    @pytest.mark.asyncio
    async def test_status_check_runs_when_lock_free(self, bt_adapter, hass):
        await bt_adapter._status_check(hass)
        assert bt_adapter._last_check is not None


class TestBluetoothAdapterStart:
    """Tests for Bluetooth adapter start method."""

    @pytest.mark.asyncio
    async def test_start_ignores_keepalive(self, bt_adapter, hass):
        await bt_adapter.start(hass, keepalive=True, status_interval=0)
        assert bt_adapter._keepalive is False

    @pytest.mark.asyncio
    async def test_start_with_status_interval(self, bt_adapter, hass):
        await bt_adapter.start(hass, keepalive=False, status_interval=30)
        assert bt_adapter._status_interval == 30
        assert bt_adapter._cancel_status is not None
        await bt_adapter.stop()


class TestBluetoothAdapterPrintOperations:
    """Smoke tests for adapter print operations through the stub transport."""

    @pytest.mark.asyncio
    async def test_print_text(self, bt_adapter, hass):
        await bt_adapter.print_text(
            hass,
            text="Hello Bluetooth",
            align="center",
            bold=True,
            cut="none",
            feed=0,
        )

    @pytest.mark.asyncio
    async def test_print_qr(self, bt_adapter, hass):
        await bt_adapter.print_qr(
            hass,
            data="https://example.com",
            size=4,
            cut="none",
            feed=0,
        )

    @pytest.mark.asyncio
    async def test_feed(self, bt_adapter, hass):
        await bt_adapter.feed(hass, lines=3)

    @pytest.mark.asyncio
    async def test_cut(self, bt_adapter, hass):
        await bt_adapter.cut(hass, mode="full")


class TestBluetoothAdapterConnectRetry:
    """Tests for the connect-time retry logic."""

    @pytest.mark.asyncio
    async def test_connect_retries_on_transient_errno(self, bt_adapter, hass):
        attempts = {"n": 0}

        class _T:
            def write(self, _data):
                pass

            def close(self):
                pass

        def _flaky(_mac, _ch, _to):
            attempts["n"] += 1
            if attempts["n"] <= 1:
                raise OSError(16, "Device or resource busy")  # EBUSY (retryable)
            return _T()

        with patch.object(bluetooth_transport, "open_rfcomm_transport", side_effect=_flaky):
            # _connect is invoked through executor by adapter ops; call directly.
            printer = await hass.async_add_executor_job(bt_adapter._connect)
        assert printer is not None
        assert attempts["n"] == 2

    @pytest.mark.asyncio
    async def test_connect_gives_up_on_non_retryable(self, bt_adapter, hass):
        def _hard_fail(_mac, _ch, _to):
            raise OSError(13, "Permission denied")  # EACCES

        with patch.object(bluetooth_transport, "open_rfcomm_transport", side_effect=_hard_fail):
            with pytest.raises(OSError, match="Permission denied"):
                await hass.async_add_executor_job(bt_adapter._connect)

    @pytest.mark.asyncio
    async def test_connect_does_not_retry_on_etimedout(self, bt_adapter, hass):
        """ETIMEDOUT must NOT retry — would balloon executor block to 12+s."""
        attempts = {"n": 0}

        def _timeout(_mac, _ch, _to):
            attempts["n"] += 1
            raise OSError(110, "Operation timed out")  # ETIMEDOUT

        with patch.object(bluetooth_transport, "open_rfcomm_transport", side_effect=_timeout):
            with pytest.raises(OSError, match="timed out"):
                await hass.async_add_executor_job(bt_adapter._connect)

        assert attempts["n"] == 1, "ETIMEDOUT should fail fast, not retry"
