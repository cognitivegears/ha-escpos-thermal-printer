"""Tests for Bluetooth Classic / RFCOMM config flow."""

import errno
from unittest.mock import patch

import pytest

from custom_components.escpos_printer._config_flow.bluetooth_helpers import (
    _bt_error_to_key,
    _can_connect_bluetooth,
    _classify_bt_error,
)
from custom_components.escpos_printer.config_flow import EscposConfigFlow
from custom_components.escpos_printer.const import (
    CONF_BT_MAC,
    CONF_CONNECTION_TYPE,
    CONF_RFCOMM_CHANNEL,
    CONNECTION_TYPE_BLUETOOTH,
)
from custom_components.escpos_printer.printer import bluetooth_transport


@pytest.fixture
def mock_paired_devices():
    """Two paired BT devices, as returned by ``_list_paired_bluetooth_devices``.

    Both advertise the imaging Class-of-Device (major class 0x06) so they
    survive the default imaging-only filter in ``_build_bt_device_choices``.
    """
    return [
        {
            "mac": "AA:BB:CC:DD:EE:FF",
            "name": "Netum NT-1809DD",
            "alias": "Netum NT-1809DD",
            "label": "Netum NT-1809DD (AA:BB:CC:DD:EE:FF)",
            "class": 0x680,  # major class 0x06 = imaging
            "is_imaging": True,
            "_choice_key": "AA:BB:CC:DD:EE:FF",
        },
        {
            "mac": "11:22:33:44:55:66",
            "name": "MUNBYN POS-58",
            "alias": "MUNBYN POS-58",
            "label": "MUNBYN POS-58 (11:22:33:44:55:66)",
            "class": 0x680,
            "is_imaging": True,
            "_choice_key": "11:22:33:44:55:66",
        },
    ]


@pytest.fixture
def mock_mixed_paired_devices():
    """One imaging device + one non-printer (phone) — exercises imaging-only filter."""
    return [
        {
            "mac": "AA:BB:CC:DD:EE:FF",
            "name": "Netum NT-1809DD",
            "alias": "Netum NT-1809DD",
            "label": "Netum NT-1809DD (AA:BB:CC:DD:EE:FF)",
            "class": 0x680,
            "is_imaging": True,
            "_choice_key": "AA:BB:CC:DD:EE:FF",
        },
        {
            "mac": "11:22:33:44:55:66",
            "name": "Pixel 8",
            "alias": "Pixel 8",
            "label": "Pixel 8 (11:22:33:44:55:66)",
            "class": 0x5A020C,  # major class 0x02 = phone
            "is_imaging": False,
            "_choice_key": "11:22:33:44:55:66",
        },
    ]


class TestConnectionTypeStep:
    """User step routes to bluetooth_select when Bluetooth is picked."""

    @pytest.mark.asyncio
    async def test_user_step_offers_bluetooth(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user()
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        # Bluetooth must be a selectable option in the dropdown
        connection_type_schema = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if k == CONF_CONNECTION_TYPE)
        ]
        assert "bluetooth" in connection_type_schema.container

    @pytest.mark.asyncio
    async def test_user_step_routes_bluetooth(self, hass, mock_paired_devices):
        flow = EscposConfigFlow()
        flow.hass = hass

        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=mock_paired_devices,
        ):
            result = await flow.async_step_user(
                {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
            )

        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_select"


class TestBluetoothSelectStep:
    """Tests for the paired-device picker."""

    @pytest.mark.asyncio
    async def test_paired_devices_shown(self, hass, mock_paired_devices):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=mock_paired_devices,
        ):
            result = await flow.async_step_bluetooth_select()

        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_select"
        # Both paired MACs and the manual fallback must be in the choices.
        bt_device = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if k == "bt_device")
        ]
        choices = bt_device.container
        assert "AA:BB:CC:DD:EE:FF" in choices
        assert "11:22:33:44:55:66" in choices
        assert "__manual__" in choices

    @pytest.mark.asyncio
    async def test_no_paired_devices_routes_to_guidance(self, hass):
        """Empty paired list shows the no_devices guidance step, not raw manual entry."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=[],
        ):
            result = await flow.async_step_bluetooth_select()

        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_no_devices"

    @pytest.mark.asyncio
    async def test_no_devices_step_submission_routes_to_manual(self, hass):
        """Submitting the no_devices form drops to manual MAC entry."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        result = await flow.async_step_bluetooth_no_devices(user_input={})
        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_manual"

    @pytest.mark.asyncio
    async def test_manual_entry_option_routes(self, hass, mock_paired_devices):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        result = await flow.async_step_bluetooth_select({"bt_device": "__manual__"})
        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_manual"

    @pytest.mark.asyncio
    async def test_select_success_advances_to_codepage(self, hass, mock_paired_devices):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        with (
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_can_connect_bluetooth",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_select(
                {
                    "bt_device": "AA:BB:CC:DD:EE:FF",
                    CONF_RFCOMM_CHANNEL: 1,
                    "timeout": 4.0,
                    "profile": "",
                }
            )

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"
        assert flow._user_data[CONF_BT_MAC] == "AA:BB:CC:DD:EE:FF"
        assert flow._user_data[CONF_RFCOMM_CHANNEL] == 1

    @pytest.mark.asyncio
    async def test_select_connection_failure_surfaces_error(
        self, hass, mock_paired_devices
    ):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        with (
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_can_connect_bluetooth",
                return_value=(False, "host_down", 112),
            ),
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_list_paired_bluetooth_devices",
                return_value=mock_paired_devices,
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_select(
                {
                    "bt_device": "AA:BB:CC:DD:EE:FF",
                    CONF_RFCOMM_CHANNEL: 1,
                    "timeout": 4.0,
                    "profile": "",
                }
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "bt_host_down"


class TestBluetoothManualStep:
    """Tests for the manual MAC entry step."""

    @pytest.mark.asyncio
    async def test_manual_step_shows_form(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        result = await flow.async_step_bluetooth_manual()
        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_manual"
        assert CONF_BT_MAC in result["data_schema"].schema
        assert CONF_RFCOMM_CHANNEL in result["data_schema"].schema

    @pytest.mark.asyncio
    async def test_manual_step_invalid_mac(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        result = await flow.async_step_bluetooth_manual(
            {
                CONF_BT_MAC: "not-a-mac",
                CONF_RFCOMM_CHANNEL: 1,
                "timeout": 4.0,
                "profile": "",
            }
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_bt_mac"

    @pytest.mark.asyncio
    async def test_manual_step_invalid_channel(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        result = await flow.async_step_bluetooth_manual(
            {
                CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
                CONF_RFCOMM_CHANNEL: 99,
                "timeout": 4.0,
                "profile": "",
            }
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_rfcomm_channel"

    @pytest.mark.asyncio
    async def test_manual_step_normalizes_mac_format(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        with (
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_can_connect_bluetooth",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_manual(
                {
                    CONF_BT_MAC: "aa-bb-cc-dd-ee-ff",
                    CONF_RFCOMM_CHANNEL: 1,
                    "timeout": 4.0,
                    "profile": "",
                }
            )

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"
        assert flow._user_data[CONF_BT_MAC] == "AA:BB:CC:DD:EE:FF"


class TestBluetoothImagingFilter:
    """The paired-device dropdown filters to imaging-class devices by default."""

    @pytest.mark.asyncio
    async def test_dropdown_hides_non_imaging_devices(self, hass, mock_mixed_paired_devices):
        """Phone (non-imaging) is hidden behind 'Show all' affordance."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=mock_mixed_paired_devices,
        ):
            result = await flow.async_step_bluetooth_select()

        bt_device = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if k == "bt_device")
        ]
        choices = bt_device.container
        assert "AA:BB:CC:DD:EE:FF" in choices  # printer kept
        assert "11:22:33:44:55:66" not in choices  # phone filtered
        assert "__show_all__" in choices  # affordance present
        assert "__manual__" in choices

    @pytest.mark.asyncio
    async def test_show_all_sentinel_disables_filter(self, hass, mock_mixed_paired_devices):
        """Picking 'Show all' re-renders with the phone visible."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_mixed_paired_devices

        result = await flow.async_step_bluetooth_select({"bt_device": "__show_all__"})

        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_select"
        bt_device = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if k == "bt_device")
        ]
        choices = bt_device.container
        assert "AA:BB:CC:DD:EE:FF" in choices
        assert "11:22:33:44:55:66" in choices  # now visible
        # No more "show all" — already at maximum
        assert "__show_all__" not in choices

    @pytest.mark.asyncio
    async def test_no_imaging_devices_falls_back_to_all(self, hass):
        """If no paired device advertises imaging class, show everything."""
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}

        # All paired devices are non-imaging (cheap printers often don't
        # advertise the class). The select step should still surface them.
        all_non_imaging = [
            {
                "mac": "AA:BB:CC:DD:EE:FF",
                "name": "Cheap Printer",
                "alias": "Cheap Printer",
                "label": "Cheap Printer (AA:BB:CC:DD:EE:FF)",
                "class": 0x000000,
                "is_imaging": False,
                "_choice_key": "AA:BB:CC:DD:EE:FF",
            },
        ]
        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=all_non_imaging,
        ):
            result = await flow.async_step_bluetooth_select()

        bt_device = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if k == "bt_device")
        ]
        choices = bt_device.container
        assert "AA:BB:CC:DD:EE:FF" in choices  # surfaced despite non-imaging


class TestBluetoothChannelHidden:
    """The RFCOMM channel field is hidden by default (almost always 1)."""

    @pytest.mark.asyncio
    async def test_channel_field_hidden_by_default(self, hass, mock_paired_devices):
        flow = EscposConfigFlow()
        flow.hass = hass
        # `show_advanced_options` reads from flow.context; default is False.
        flow.context = {"source": "user", "show_advanced_options": False}
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=mock_paired_devices,
        ):
            result = await flow.async_step_bluetooth_select()

        schema_keys = {str(k) for k in result["data_schema"].schema}
        assert "rfcomm_channel" not in schema_keys

    @pytest.mark.asyncio
    async def test_channel_field_visible_with_advanced_options(
        self, hass, mock_paired_devices
    ):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow.context = {"source": "user", "show_advanced_options": True}
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        with patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps."
            "_list_paired_bluetooth_devices",
            return_value=mock_paired_devices,
        ):
            result = await flow.async_step_bluetooth_select()

        schema_keys = {str(k) for k in result["data_schema"].schema}
        assert "rfcomm_channel" in schema_keys


class TestBluetoothChannelRetry:
    """A channel_refused failure routes to the channel-retry step."""

    @pytest.mark.asyncio
    async def test_channel_refused_routes_to_retry_step(
        self, hass, mock_paired_devices
    ):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow.context = {"source": "user", "show_advanced_options": False}
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        with (
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_can_connect_bluetooth",
                return_value=(False, "channel_refused", 111),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_select(
                {
                    "bt_device": "AA:BB:CC:DD:EE:FF",
                    "timeout": 4.0,
                    "profile": "",
                }
            )

        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_channel_retry"

    @pytest.mark.asyncio
    async def test_retry_step_with_valid_channel_advances(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._pending_bt = {
            "mac": "AA:BB:CC:DD:EE:FF",
            "channel": 1,
            "timeout": 4.0,
            "profile": "",
            "printer_name": "Test Printer",
        }

        with (
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_can_connect_bluetooth",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_channel_retry(
                {"rfcomm_channel": 2}
            )

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"


class TestBluetoothErrnoClassification:
    """Errno-to-error-code mapping (Q-H1 / S-M6)."""

    @pytest.mark.parametrize(
        ("errno_val", "expected_code"),
        [
            (errno.EACCES, "permission_denied"),
            (errno.EPERM, "permission_denied"),
            (errno.ETIMEDOUT, "timeout"),
            (errno.EHOSTUNREACH, "host_down"),
            (errno.ENETUNREACH, "host_down"),
            (errno.ECONNREFUSED, "channel_refused"),
            (errno.ENODEV, "device_not_found"),
            (errno.EAFNOSUPPORT, "unavailable"),
            (errno.EPROTONOSUPPORT, "unavailable"),
        ],
    )
    def test_classify_known_errno(self, errno_val, expected_code):
        exc = OSError(errno_val, "irrelevant text")
        assert _classify_bt_error(exc) == expected_code

    def test_classify_unknown_errno_returns_none(self):
        exc = OSError(99999, "some weird error")
        assert _classify_bt_error(exc) is None

    @pytest.mark.parametrize(
        ("text", "expected_code"),
        [
            ("Permission denied", "permission_denied"),
            ("Operation timed out", "timeout"),
            ("Host is down", "host_down"),
            ("Network is unreachable", "host_down"),
            ("Connection refused", "channel_refused"),
            ("Address family not supported by protocol", "unavailable"),
            ("No such device", "device_not_found"),
        ],
    )
    def test_classify_substring_fallback_when_errno_missing(self, text, expected_code):
        exc = OSError(text)  # no errno
        assert _classify_bt_error(exc) == expected_code

    def test_error_key_for_channel_refused(self):
        assert _bt_error_to_key("channel_refused") == "bt_channel_refused"

    def test_error_key_fallback(self):
        assert _bt_error_to_key(None) == "cannot_connect_bt"
        assert _bt_error_to_key("nonsense") == "cannot_connect_bt"

    def test_can_connect_caps_probe_timeout(self, monkeypatch):
        """A 60s configured timeout must be capped at 5s for the probe."""
        captured = {}

        def _fake(_mac, _ch, timeout):
            captured["timeout"] = timeout
            raise OSError(errno.ETIMEDOUT, "timed out")

        monkeypatch.setattr(bluetooth_transport, "open_rfcomm_transport", _fake)
        ok, code, _err_no = _can_connect_bluetooth("AA:BB:CC:DD:EE:FF", 1, 60.0)
        assert ok is False
        assert code == "timeout"
        assert captured["timeout"] == 5.0


class TestBluetoothUniqueId:
    """Verify unique-ID dedupe for Bluetooth printers."""

    @pytest.mark.asyncio
    async def test_unique_id_uses_mac(self, hass, mock_paired_devices):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
        flow._paired_bt_devices = mock_paired_devices

        captured = {}

        async def _capture(uid):
            captured["uid"] = uid

        with (
            patch(
                "custom_components.escpos_printer._config_flow.bluetooth_steps."
                "_can_connect_bluetooth",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", side_effect=_capture),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            await flow.async_step_bluetooth_select(
                {
                    "bt_device": "AA:BB:CC:DD:EE:FF",
                    CONF_RFCOMM_CHANNEL: 1,
                    "timeout": 4.0,
                    "profile": "",
                }
            )

        assert captured["uid"] == "bt:aa:bb:cc:dd:ee:ff"
