"""Tests for the shared DeviceInfo builder (custom_components/escpos_printer/device.py)."""

from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONF_DETECTED_MANUFACTURER,
    CONF_DETECTED_MODEL,
    CONF_MAC_ADDRESS,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
)
from custom_components.escpos_printer.device import build_device_info


class _FakeEntry:
    def __init__(
        self,
        entry_id: str = "abc",
        title: str = "My Printer",
        data: dict[str, Any] | None = None,
        unique_id: str | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}
        self.unique_id = unique_id


def test_model_by_connection_type() -> None:
    cases = {
        CONNECTION_TYPE_NETWORK: "Network Printer",
        CONNECTION_TYPE_USB: "USB Printer",
        CONNECTION_TYPE_BLUETOOTH: "Bluetooth Printer",
        CONNECTION_TYPE_SERIAL: "Serial Printer",
    }
    for connection_type, expected_model in cases.items():
        entry = _FakeEntry(data={CONF_CONNECTION_TYPE: connection_type})
        info = build_device_info(entry)  # type: ignore[arg-type]
        assert info["model"] == expected_model
        assert info["manufacturer"] == "ESC/POS"
        assert info["name"] == "ESC/POS Printer My Printer"


def test_usb_serial_number_parsed_from_unique_id() -> None:
    entry = _FakeEntry(
        data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB},
        unique_id="usb:04b8:0e03:ABC123",
    )
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert info.get("serial_number") == "ABC123"


def test_usb_serial_number_prefers_entry_data_over_unique_id() -> None:
    entry = _FakeEntry(
        data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB, "serial_number": "FROM-DATA"},
        unique_id="usb:04b8:0e03:FROM-UNIQUE-ID",
    )
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert info.get("serial_number") == "FROM-DATA"


def test_usb_serial_number_absent_when_unique_id_has_no_serial() -> None:
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}, unique_id="usb:04b8:0e03")
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert "serial_number" not in info


def test_usb_serial_number_absent_when_unique_id_has_endpoint_suffix() -> None:
    """Endpoint-folded unique_ids (usb:VID:PID:in_ep:out_ep) have no serial segment.

    Regression test: parts[3] used to be returned as a "serial" here, but
    it's actually the in-endpoint hex from _generate_usb_unique_id's
    endpoint-folding (see _config_flow/usb_steps.py).
    """
    entry = _FakeEntry(
        data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}, unique_id="usb:04b8:0e03:81:03"
    )
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert "serial_number" not in info


def test_usb_serial_number_absent_when_unique_id_has_empty_trailing_segment() -> None:
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}, unique_id="usb:04b8:0e03:")
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert "serial_number" not in info


def test_non_usb_transports_never_get_serial_number() -> None:
    entry = _FakeEntry(
        data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK, "serial_number": "ignored"}
    )
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert "serial_number" not in info


def test_device_info_prefers_detected_fields() -> None:
    entry = _FakeEntry(
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            CONF_DETECTED_MANUFACTURER: "EPSON",
            CONF_DETECTED_MODEL: "TM-T20II",
        }
    )
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert info["manufacturer"] == "EPSON"
    assert info["model"] == "TM-T20II"


def test_device_info_falls_back_without_detected_fields() -> None:
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert info["manufacturer"] == "ESC/POS"
    assert info["model"] == "Network Printer"


def test_device_info_includes_mac_connection_when_tracked() -> None:
    entry = _FakeEntry(
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            CONF_MAC_ADDRESS: "50:57:9c:62:8e:52",
        }
    )
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert info["connections"] == {(CONNECTION_NETWORK_MAC, "50:57:9c:62:8e:52")}


def test_device_info_no_connections_without_mac() -> None:
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    info = build_device_info(entry)  # type: ignore[arg-type]
    assert "connections" not in info
