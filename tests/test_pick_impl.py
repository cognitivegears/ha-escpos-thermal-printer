"""Tests for profile-driven image implementation selection."""

from custom_components.escpos_printer.capabilities.features import (
    pick_impl,
    profile_declares_no_images,
)
from custom_components.escpos_printer.const import RELIABILITY_PROFILE_PRESETS


def test_raster_preferred() -> None:
    assert pick_impl("TM-T20II") == "bitImageRaster"


def test_column_only_impact_printer() -> None:
    assert pick_impl("TM-U220") == "bitImageColumn"


def test_no_image_profile() -> None:
    assert pick_impl("AF-240") is None
    assert profile_declares_no_images("AF-240") is True


def test_unknown_and_auto_profiles() -> None:
    assert pick_impl("") is None
    assert pick_impl(None) is None
    assert pick_impl("no-such-profile") is None
    assert profile_declares_no_images("") is False
    assert profile_declares_no_images("no-such-profile") is False


def test_graphics_never_auto_picked() -> None:
    # Every bundled profile with graphics also has raster; the picker
    # must never return "graphics".
    assert pick_impl("TM-T88V") == "bitImageRaster"


def test_presets_are_pacing_only() -> None:
    for name, preset in RELIABILITY_PROFILE_PRESETS.items():
        assert "impl" not in preset, f"preset {name} must not set impl"
