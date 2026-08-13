"""Tests for the RP820 custom profile (custom_profiles.py)."""

from __future__ import annotations

import escpos.capabilities

from custom_components.escpos_printer._config_flow.calibration import CODEPAGE_CANDIDATES
from custom_components.escpos_printer.capabilities.aliases import normalize_model, resolve_alias
from custom_components.escpos_printer.capabilities.codepages import get_profile_codepages
from custom_components.escpos_printer.capabilities.custom_profiles import (
    register_custom_profiles,
)
from custom_components.escpos_printer.capabilities.line_widths import get_profile_line_widths
from custom_components.escpos_printer.capabilities.loader import _get_capabilities
from custom_components.escpos_printer.capabilities.profiles import get_profile_choices


def test_registers_rp820_in_escpos_capabilities() -> None:
    register_custom_profiles()
    profile = escpos.capabilities.get_profile("RP820")
    assert profile.profile_data["codePages"]["0"] == "CP437"
    assert profile.profile_data["codePages"]["2"] == "CP850"
    assert profile.profile_data["codePages"]["16"] == "CP1252"
    assert profile.profile_data["codePages"]["19"] == "CP858"
    assert profile.profile_data["media"]["width"]["pixels"] == 576
    assert profile.profile_data["features"]["graphics"] is False
    assert profile.profile_data["fonts"]["0"]["columns"] == 48


def test_registration_is_idempotent() -> None:
    """A second call must not rebind the dict escpos's CLASS_CACHE already
    built a profile class from -- otherwise get_profile("RP820") would
    return stale data out of sync with the registered dict."""
    register_custom_profiles()
    register_custom_profiles()
    profile = escpos.capabilities.get_profile("RP820")
    assert profile.profile_data is escpos.capabilities.CAPABILITIES["profiles"]["RP820"]


def test_rp820_profile_present_in_our_capabilities_loader() -> None:
    profiles = _get_capabilities()["profiles"]
    assert "RP820" in profiles


def test_rp850p_alias_resolves_to_rp820() -> None:
    assert resolve_alias("Rongta RP850P") == "RP820"
    assert resolve_alias("RP850P") == "RP820"


def test_calibration_codepage_candidates_for_rp820() -> None:
    profile_codepages = get_profile_codepages("RP820")
    candidates = tuple(cp for cp in CODEPAGE_CANDIDATES if cp in profile_codepages)
    assert candidates == ("CP858", "CP1252", "CP850", "CP437")


def test_dropdown_lists_rp820_exactly_once_without_compatible_suffix() -> None:
    choices = get_profile_choices()
    display_names = [display for _key, display in choices]
    assert display_names.count("Rongta RP820") == 1
    assert "Rongta RP820 (compatible)" not in display_names


# =============================================================================
# Bundled-profile runtime patches (escpos-printer-db data bugs, also
# reported upstream)
# =============================================================================


def test_nt80vul_codepages_deduped() -> None:
    register_custom_profiles()
    code_pages = escpos.capabilities.get_profile("NT-80-V-UL").get_code_pages()
    assert code_pages["CP437"] == "0"
    assert code_pages["CP1252"] == "16"
    assert code_pages["CP858"] == "19"
    assert code_pages["CP850"] == "2"


def test_pos5890_codepages_deduped() -> None:
    register_custom_profiles()
    code_pages = escpos.capabilities.get_profile("POS-5890").get_code_pages()
    assert code_pages["CP437"] == "0"
    assert code_pages["CP1252"] == "16"
    assert code_pages["CP858"] == "19"


def test_nt5890k_codepages_deduped() -> None:
    register_custom_profiles()
    code_pages = escpos.capabilities.get_profile("NT-5890K").get_code_pages()
    assert code_pages["CP437"] == "0"
    assert code_pages["CP1252"] == "16"
    assert code_pages["CP858"] == "19"


def test_ct_s651_codepages_unchanged_by_dedupe() -> None:
    """CT-S651 has real low-index duplicates (CP1252 at 9 and 16, CP852 at
    6 and 18, CP866 at 7 and 17) with no >=48 entry -- the dedupe rule
    must be a strict no-op here. This is the regression guard for the
    "lowest index always wins" mistake: that rule would have deleted the
    working low duplicate (9/6/7) on this profile."""
    before = dict(escpos.capabilities.CAPABILITIES["profiles"]["CT-S651"]["codePages"])
    register_custom_profiles()
    after = dict(escpos.capabilities.CAPABILITIES["profiles"]["CT-S651"]["codePages"])
    assert after == before


def test_nt80vul_font_columns_corrected() -> None:
    register_custom_profiles()
    profile_data = escpos.capabilities.get_profile("NT-80-V-UL").profile_data
    assert profile_data["fonts"]["0"]["columns"] == 48
    assert profile_data["fonts"]["1"]["columns"] == 64


def test_nt80vul_patch_is_idempotent() -> None:
    register_custom_profiles()
    first = dict(escpos.capabilities.CAPABILITIES["profiles"]["NT-80-V-UL"])
    register_custom_profiles()
    second = dict(escpos.capabilities.CAPABILITIES["profiles"]["NT-80-V-UL"])
    assert first == second


def test_aliased_model_through_nt80vul_gets_corrected_line_widths() -> None:
    """Xprinter XP-80C routes through NT-80-V-UL; its columns should now
    reflect the corrected profile data (48, 64), not the plausibility-filter
    fallback to common widths."""
    register_custom_profiles()
    alias_key = normalize_model("Xprinter XP-80C")
    assert get_profile_line_widths(alias_key) == [48, 64]
