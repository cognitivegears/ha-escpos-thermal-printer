"""Tests for the Fichero D11s label preset."""

from custom_components.escpos_printer.capabilities.ble_profiles import get_ble_profiles


def test_fichero_d11s_label_profile():
    """The D11s uses a 96-dot printhead and 240 raster rows on 30 mm labels."""
    profile = get_ble_profiles()["fichero_label_d11s"]
    assert profile.width == 96
    assert profile.dialect == "aiyin"
    assert profile.label_rows == 240
    assert profile.matches_advertisement("FICHERO_5836")
    assert profile.matches_advertisement("D11s_1234")
    assert profile.matches_model("d11s")
    assert profile.matches_model("FICHERO_5836")
    assert not profile.matches_model("FICHERO_6181")
    assert not profile.matches_model("Fichero 3561")
