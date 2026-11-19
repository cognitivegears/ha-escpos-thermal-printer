"""Tests for the 203 dpi Fichero Mini Pocket Printer preset."""

from custom_components.escpos_printer.capabilities.ble_profiles import get_ble_profiles


def test_fichero_mini_pocket_profile():
    """The Fichero 3561 uses a 384-dot continuous-paper raster."""
    profile = get_ble_profiles()["fichero_mini_pocket"]
    assert profile.width == 384
    assert profile.dialect == "lujiang"
    assert profile.label_rows == 0
    assert profile.matches_advertisement("Fichero 3561")
    assert profile.matches_model("DP-D1")
    assert profile.matches_model("Fichero 3561")
    assert not profile.matches_model("DP_D1H")
    assert not profile.matches_model("D11s")
