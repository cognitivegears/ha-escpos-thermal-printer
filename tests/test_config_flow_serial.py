"""Tests for serial printer config flow."""

import errno
from unittest.mock import patch

import pytest

from custom_components.escpos_printer._config_flow.serial_helpers import (
    _can_connect_serial,
    _classify_serial_error,
    _serial_error_to_key,
)
from custom_components.escpos_printer._config_flow.serial_steps import (
    _MANUAL_ENTRY,
    _get_serial_port_choices,
)
from custom_components.escpos_printer.config_flow import EscposConfigFlow
from custom_components.escpos_printer.const import (
    CONF_BAUDRATE,
    CONF_CONNECTION_TYPE,
    CONF_SERIAL_PORT,
    CONNECTION_TYPE_SERIAL,
)

_MOCK_PORTS = {
    "/dev/ttyUSB0": "/dev/ttyUSB0 — USB Serial Device (s/n: ABC123)",
    "/dev/ttyACM0": "/dev/ttyACM0 — Arduino Uno",
}


def _patch_ports(ports=_MOCK_PORTS):
    return patch(
        "custom_components.escpos_printer._config_flow.serial_steps._get_serial_port_choices",
        return_value=ports,
    )


class TestConnectionTypeStep:
    """User step routes to serial picker when Serial is chosen."""

    @pytest.mark.asyncio
    async def test_user_step_offers_serial(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass

        result = await flow.async_step_user()
        assert result["type"] == "form"
        assert result["step_id"] == "user"
        connection_type_schema = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if k == CONF_CONNECTION_TYPE)
        ]
        assert "serial" in connection_type_schema.container

    @pytest.mark.asyncio
    async def test_user_step_routes_serial(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass

        with _patch_ports():
            result = await flow.async_step_user({CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL})

        assert result["type"] == "form"
        assert result["step_id"] == "serial"


class TestSerialPickerStep:
    """Tests for the port picker step (async_step_serial)."""

    @pytest.mark.asyncio
    async def test_shows_picker_form(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        with _patch_ports():
            result = await flow.async_step_serial()

        assert result["type"] == "form"
        assert result["step_id"] == "serial"

    @pytest.mark.asyncio
    async def test_picker_includes_manual_option(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        with _patch_ports():
            result = await flow.async_step_serial()

        # The schema is vol.In(dict) — keys are the selectable values.
        schema_validator = result["data_schema"].schema[
            next(k for k in result["data_schema"].schema if str(k) == CONF_SERIAL_PORT)
        ]
        assert _MANUAL_ENTRY in schema_validator.container
        assert "/dev/ttyUSB0" in schema_validator.container

    @pytest.mark.asyncio
    async def test_no_ports_skips_to_manual(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        with _patch_ports({}):
            result = await flow.async_step_serial()

        assert result["type"] == "form"
        assert result["step_id"] == "serial_manual"

    @pytest.mark.asyncio
    async def test_picking_port_advances_to_config(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        with _patch_ports():
            result = await flow.async_step_serial({CONF_SERIAL_PORT: "/dev/ttyUSB0"})

        assert result["type"] == "form"
        assert result["step_id"] == "serial_config"
        assert flow._user_data[CONF_SERIAL_PORT] == "/dev/ttyUSB0"

    @pytest.mark.asyncio
    async def test_manual_entry_sentinel_routes_to_manual(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        with _patch_ports():
            result = await flow.async_step_serial({CONF_SERIAL_PORT: _MANUAL_ENTRY})

        assert result["type"] == "form"
        assert result["step_id"] == "serial_manual"


class TestSerialManualStep:
    """Tests for the manual port entry step (async_step_serial_manual)."""

    @pytest.mark.asyncio
    async def test_shows_form_on_init(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        result = await flow.async_step_serial_manual()
        assert result["type"] == "form"
        assert result["step_id"] == "serial_manual"

    @pytest.mark.asyncio
    async def test_empty_port_returns_error(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        result = await flow.async_step_serial_manual({CONF_SERIAL_PORT: ""})
        assert result["type"] == "form"
        assert result["errors"]["base"] == "serial_port_not_found"

    @pytest.mark.asyncio
    async def test_valid_port_advances_to_config(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        result = await flow.async_step_serial_manual({CONF_SERIAL_PORT: "/dev/ttyUSB0"})
        assert result["type"] == "form"
        assert result["step_id"] == "serial_config"
        assert flow._user_data[CONF_SERIAL_PORT] == "/dev/ttyUSB0"

    @pytest.mark.asyncio
    async def test_url_port_advances_to_config(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL}

        result = await flow.async_step_serial_manual(
            {CONF_SERIAL_PORT: "esphome://192.168.1.100:6638"}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "serial_config"
        assert flow._user_data[CONF_SERIAL_PORT] == "esphome://192.168.1.100:6638"


class TestSerialConfigStep:
    """Tests for the baudrate/timeout/profile step (async_step_serial_config)."""

    @pytest.mark.asyncio
    async def test_shows_form_on_init(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        }

        result = await flow.async_step_serial_config()
        assert result["type"] == "form"
        assert result["step_id"] == "serial_config"

    @pytest.mark.asyncio
    async def test_invalid_baudrate_returns_error(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        }

        result = await flow.async_step_serial_config(
            {CONF_BAUDRATE: 1234, "timeout": 4.0, "profile": ""}
        )
        assert result["type"] == "form"
        assert result["errors"]["base"] == "invalid_baudrate"

    @pytest.mark.asyncio
    async def test_successful_connection_advances_to_codepage(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        }

        with (
            patch(
                "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_serial_config(
                {CONF_BAUDRATE: 9600, "timeout": 4.0, "profile": ""}
            )

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"
        assert flow._user_data[CONF_SERIAL_PORT] == "/dev/ttyUSB0"
        assert flow._user_data[CONF_BAUDRATE] == 9600
        assert flow._user_data[CONF_CONNECTION_TYPE] == CONNECTION_TYPE_SERIAL

    @pytest.mark.asyncio
    async def test_url_based_port_advances_to_codepage(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "esphome://192.168.1.100:6638",
        }

        with (
            patch(
                "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
                return_value=(True, None, None),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_serial_config(
                {CONF_BAUDRATE: 9600, "timeout": 4.0, "profile": ""}
            )

        assert result["type"] == "form"
        assert result["step_id"] == "codepage"
        assert flow._user_data[CONF_SERIAL_PORT] == "esphome://192.168.1.100:6638"

    @pytest.mark.asyncio
    async def test_connection_failure_shows_error(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        }

        with (
            patch(
                "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
                return_value=(False, "serial_port_not_found", 2),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_serial_config(
                {CONF_BAUDRATE: 9600, "timeout": 4.0, "profile": ""}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "serial_port_not_found"

    @pytest.mark.asyncio
    async def test_permission_denied_shows_error(self, hass):
        flow = EscposConfigFlow()
        flow.hass = hass
        flow._user_data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        }

        with (
            patch(
                "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
                return_value=(False, "serial_permission_denied", 13),
            ),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_serial_config(
                {CONF_BAUDRATE: 9600, "timeout": 4.0, "profile": ""}
            )

        assert result["type"] == "form"
        assert result["errors"]["base"] == "serial_permission_denied"


class TestGetSerialPortChoices:
    """Tests for the _get_serial_port_choices helper."""

    def test_returns_dict_with_device_paths(self):
        mock_port = type(
            "Port",
            (),
            {
                "device": "/dev/ttyUSB0",
                "description": "USB Serial Device",
                "serial_number": "ABC123",
                "manufacturer": "FTDI",
            },
        )()

        with patch(
            "custom_components.escpos_printer._config_flow.serial_steps._comports",
            return_value=[mock_port],
        ):
            result = _get_serial_port_choices()

        assert "/dev/ttyUSB0" in result
        assert "USB Serial Device" in result["/dev/ttyUSB0"]
        assert "ABC123" in result["/dev/ttyUSB0"]

    def test_returns_empty_dict_when_no_ports(self):
        with patch(
            "custom_components.escpos_printer._config_flow.serial_steps._comports",
            return_value=[],
        ):
            result = _get_serial_port_choices()

        assert result == {}

    def test_skips_na_description(self):
        mock_port = type(
            "Port",
            (),
            {"device": "/dev/ttyS0", "description": "n/a", "serial_number": None},
        )()

        with patch(
            "custom_components.escpos_printer._config_flow.serial_steps._comports",
            return_value=[mock_port],
        ):
            result = _get_serial_port_choices()

        assert result["/dev/ttyS0"] == "/dev/ttyS0"


class TestSerialHelpers:
    """Tests for serial connection probe helpers."""

    def test_classify_serial_error_eacces(self):
        exc = OSError("permission denied")
        exc.errno = errno.EACCES
        assert _classify_serial_error(exc) == "serial_permission_denied"

    def test_classify_serial_error_enoent(self):
        exc = OSError("no such file")
        exc.errno = errno.ENOENT
        assert _classify_serial_error(exc) == "serial_port_not_found"

    def test_classify_serial_error_ebusy(self):
        exc = OSError("device busy")
        exc.errno = errno.EBUSY
        assert _classify_serial_error(exc) == "serial_port_busy"

    def test_classify_serial_error_text_fallback_permission(self):
        exc = OSError("Access denied to port")
        exc.errno = None
        assert _classify_serial_error(exc) == "serial_permission_denied"

    def test_classify_serial_error_text_fallback_not_found(self):
        exc = OSError("Port not found")
        exc.errno = None
        assert _classify_serial_error(exc) == "serial_port_not_found"

    def test_classify_serial_error_unknown(self):
        exc = OSError("some unexpected error")
        exc.errno = 999
        assert _classify_serial_error(exc) is None

    def test_can_connect_serial_success(self):
        from custom_components.escpos_printer.printer import serial_transport

        mock_transport = object()
        with patch.object(serial_transport, "open_serial_transport", return_value=mock_transport):
            ok, code, err_no = _can_connect_serial("/dev/ttyUSB0", 9600, 4.0)

        assert ok is True
        assert code is None
        assert err_no is None

    def test_can_connect_serial_failure_enoent(self):
        from custom_components.escpos_printer.printer import serial_transport

        exc = OSError("no such file")
        exc.errno = errno.ENOENT
        with patch.object(serial_transport, "open_serial_transport", side_effect=exc):
            ok, code, err_no = _can_connect_serial("/dev/ttyUSB0", 9600, 4.0)

        assert ok is False
        assert code == "serial_port_not_found"
        assert err_no == errno.ENOENT

    def test_serial_error_to_key_known(self):
        assert _serial_error_to_key("serial_permission_denied") == "serial_permission_denied"
        assert _serial_error_to_key("serial_port_not_found") == "serial_port_not_found"
        assert _serial_error_to_key("serial_port_busy") == "serial_port_busy"

    def test_serial_error_to_key_unknown_falls_back(self):
        assert _serial_error_to_key(None) == "cannot_connect_serial"
        assert _serial_error_to_key("some_unknown_code") == "cannot_connect_serial"
