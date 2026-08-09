"""Tests for the per-entry paper width override."""

from custom_components.escpos_printer.printer import create_printer_adapter
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig


def test_width_override_beats_profile() -> None:
    # TM-T20II declares 576px; use a distinct override value so this test
    # actually proves the override wins rather than coincidentally matching.
    config = NetworkPrinterConfig(host="127.0.0.1", profile="TM-T20II", width_pixels=384)
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 384


def test_width_override_without_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile=None, width_pixels=384)
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 384


def test_no_override_uses_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile="TM-T20II")
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 576  # TM-T20II declares 576px
