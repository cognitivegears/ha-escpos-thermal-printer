"""Direct tests for the USB enumeration helpers in ``_config_flow.usb_helpers``.

The config-flow tests in ``test_config_flow_usb.py`` mock
``_discover_usb_printers`` at the import site, so the actual
``_enumerate_usb_devices`` loop is never executed. These tests mock
``usb.core`` / ``usb.util`` instead so we exercise the iteration,
descriptor-string error handling, and the two thin wrappers
(``_discover_usb_printers`` filters by VID + strips
``is_known_printer``; ``_discover_all_usb_devices`` returns every
device with the flag intact).
"""

from __future__ import annotations

import sys
import types
from typing import Any

import pytest

from custom_components.escpos_printer._config_flow import usb_helpers
from custom_components.escpos_printer.const import THERMAL_PRINTER_VIDS


class _FakeDevice:
    """Minimal stand-in for ``usb.core.Device`` used in enumeration tests."""

    # pyusb exposes camelCase descriptor attributes (idVendor, idProduct,
    # iManufacturer, …); the SUT reads them by name, so the fake keeps
    # the same casing to stay byte-for-byte compatible with the real API.
    # Accepting a generic kwarg bag lets us mirror pyusb's casing without
    # tripping ruff's lowercase-argument lint, which doesn't apply to a
    # third-party API contract.
    def __init__(self, **kwargs: int) -> None:
        defaults = {
            "idVendor": 0,
            "idProduct": 0,
            "iManufacturer": 1,
            "iProduct": 2,
            "iSerialNumber": 3,
        }
        for name, default in defaults.items():
            setattr(self, name, kwargs.get(name, default))


def _install_fake_usb(
    monkeypatch: pytest.MonkeyPatch,
    *,
    devices: list[_FakeDevice] | None = None,
    find_raises: BaseException | None = None,
    string_overrides: dict[int, str] | None = None,
    string_raises_for: set[int] | None = None,
    serial_raises: bool = False,
) -> None:
    """Install fake ``usb.core`` / ``usb.util`` modules for one test."""
    usb_pkg = types.ModuleType("usb")
    usb_core = types.ModuleType("usb.core")
    usb_util = types.ModuleType("usb.util")

    def find(find_all: bool = False) -> Any:
        if find_raises is not None:
            raise find_raises
        return iter(devices or [])

    usb_core.find = find  # type: ignore[attr-defined]

    string_overrides = string_overrides or {}
    string_raises_for = string_raises_for or set()

    def get_string(device: _FakeDevice, index: int) -> str:
        if index in string_raises_for:
            raise OSError("simulated descriptor read failure")
        if serial_raises and index == device.iSerialNumber:
            raise OSError("permission denied")
        return string_overrides.get(index, f"str-{index}")

    usb_util.get_string = get_string  # type: ignore[attr-defined]

    # The late ``import usb.core`` statement in the SUT both inserts
    # the submodule into ``sys.modules`` *and* sets it as an attribute
    # on the parent ``usb`` package. We have to mimic both so the
    # subsequent ``usb.core.find`` lookup resolves to our fake.
    usb_pkg.core = usb_core  # type: ignore[attr-defined]
    usb_pkg.util = usb_util  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "usb", usb_pkg)
    monkeypatch.setitem(sys.modules, "usb.core", usb_core)
    monkeypatch.setitem(sys.modules, "usb.util", usb_util)


def test_enumerate_returns_empty_list_when_pyusb_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the late ``import usb.core`` to fail by removing it from
    # sys.modules and shadowing the parent with a broken module.
    monkeypatch.setitem(sys.modules, "usb", None)
    monkeypatch.setitem(sys.modules, "usb.core", None)
    monkeypatch.setitem(sys.modules, "usb.util", None)
    assert usb_helpers._enumerate_usb_devices(None, default_product="X") == []


def test_enumerate_returns_empty_list_when_find_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_usb(monkeypatch, find_raises=RuntimeError("libusb backend missing"))
    # Exception inside ``usb.core.find`` is logged at debug and
    # produces an empty list — the integration must not crash if libusb
    # isn't installed on the host.
    assert usb_helpers._enumerate_usb_devices(None, default_product="X") == []


def test_enumerate_filters_by_vid_when_filter_provided(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known_vid = next(iter(THERMAL_PRINTER_VIDS))
    other_vid = 0xDEAD
    assert other_vid not in THERMAL_PRINTER_VIDS
    _install_fake_usb(
        monkeypatch,
        devices=[
            _FakeDevice(idVendor=known_vid, idProduct=0x0001),
            _FakeDevice(idVendor=other_vid, idProduct=0x0002),
        ],
    )
    out = usb_helpers._enumerate_usb_devices(
        THERMAL_PRINTER_VIDS, default_product="Thermal Printer"
    )
    assert len(out) == 1
    assert out[0]["vendor_id"] == known_vid
    assert out[0]["is_known_printer"] is True


def test_enumerate_unfiltered_marks_unknown_vendors_as_non_printer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_vid = 0xDEAD
    assert other_vid not in THERMAL_PRINTER_VIDS
    _install_fake_usb(
        monkeypatch, devices=[_FakeDevice(idVendor=other_vid, idProduct=0x0002)]
    )
    out = usb_helpers._enumerate_usb_devices(None, default_product="USB Device")
    assert len(out) == 1
    assert out[0]["vendor_id"] == other_vid
    assert out[0]["is_known_printer"] is False
    assert out[0]["product"] == "str-2"
    assert out[0]["serial_number"] == "str-3"


def test_enumerate_swallows_serial_descriptor_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_usb(
        monkeypatch,
        devices=[_FakeDevice(idVendor=0x04B8, idProduct=0x0001)],
        serial_raises=True,
    )
    out = usb_helpers._enumerate_usb_devices(None, default_product="USB Device")
    # Serial read failed but the other descriptors were valid, so we
    # keep the entry and just record ``serial_number=None``.
    assert len(out) == 1
    assert out[0]["serial_number"] is None
    assert out[0]["manufacturer"] == "str-1"


def test_enumerate_falls_back_to_default_label_on_manufacturer_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    device = _FakeDevice(idVendor=0x04B8, idProduct=0x0001)
    _install_fake_usb(
        monkeypatch,
        devices=[device],
        # ``iManufacturer`` read fails → outer except triggers the
        # fallback entry with default product / Unknown manufacturer.
        string_raises_for={device.iManufacturer},
    )
    out = usb_helpers._enumerate_usb_devices(None, default_product="USB Device")
    assert len(out) == 1
    assert out[0]["manufacturer"] == "Unknown"
    assert out[0]["product"] == "USB Device"
    assert out[0]["serial_number"] is None
    assert "USB Device" in out[0]["label"]


def test_enumerate_handles_device_with_no_serial_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # ``iSerialNumber == 0`` means the descriptor has no serial string;
    # ``get_string`` must not be called for it.
    device = _FakeDevice(idVendor=0x04B8, idProduct=0x0001, iSerialNumber=0)
    _install_fake_usb(monkeypatch, devices=[device])
    out = usb_helpers._enumerate_usb_devices(None, default_product="USB Device")
    assert len(out) == 1
    assert out[0]["serial_number"] is None


def test_discover_usb_printers_strips_is_known_printer_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    known_vid = next(iter(THERMAL_PRINTER_VIDS))
    _install_fake_usb(
        monkeypatch, devices=[_FakeDevice(idVendor=known_vid, idProduct=0x0001)]
    )
    out = usb_helpers._discover_usb_printers()
    assert len(out) == 1
    # Printer-only listing intentionally drops the flag — every entry
    # is a printer, so the flag is redundant.
    assert "is_known_printer" not in out[0]


def test_discover_all_usb_devices_keeps_is_known_printer_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_vid = 0xDEAD
    assert other_vid not in THERMAL_PRINTER_VIDS
    _install_fake_usb(
        monkeypatch, devices=[_FakeDevice(idVendor=other_vid, idProduct=0x0002)]
    )
    out = usb_helpers._discover_all_usb_devices()
    assert len(out) == 1
    assert out[0]["is_known_printer"] is False
