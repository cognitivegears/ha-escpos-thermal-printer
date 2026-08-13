"""Tests for the RP820/TM-m30III custom profiles (custom_profiles.py)."""

from __future__ import annotations

import escpos.capabilities

from custom_components.escpos_printer._config_flow.calibration import CODEPAGE_CANDIDATES
from custom_components.escpos_printer.capabilities.aliases import normalize_model, resolve_alias
from custom_components.escpos_printer.capabilities.codepages import get_profile_codepages
from custom_components.escpos_printer.capabilities.custom_profiles import (
    _register_rp820,
    _register_tm_m10,
    _register_tm_m30iii,
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


# =============================================================================
# Epson TM-T70/TM-T70II/TM-m30 support (upstream escpos-printer-db merges
# newer than python-escpos 3.1's bundled database)
# =============================================================================


def test_registers_tm_m30iii_in_escpos_capabilities() -> None:
    register_custom_profiles()
    profile = escpos.capabilities.get_profile("TM-m30III")
    assert profile.profile_data["media"]["width"]["pixels"] == 576
    assert profile.profile_data["fonts"]["0"]["columns"] == 48
    assert profile.profile_data["fonts"]["1"]["columns"] == 57
    assert profile.profile_data["fonts"]["2"]["columns"] == 64
    assert profile.profile_data["codePages"]["0"] == "CP437"
    assert profile.profile_data["codePages"]["2"] == "CP850"
    assert profile.profile_data["codePages"]["16"] == "CP1252"
    # The honesty property that makes this a standalone profile rather
    # than an alias to another 80mm/576px bundled profile: index 19 is
    # NOT CP858 here, unlike TM-T20II/NT-80-V-UL/POS-5890/etc.
    assert profile.profile_data["codePages"].get("19") != "CP858"


def test_tm_m30iii_registration_is_idempotent() -> None:
    register_custom_profiles()
    register_custom_profiles()
    profile = escpos.capabilities.get_profile("TM-m30III")
    assert profile.profile_data is escpos.capabilities.CAPABILITIES["profiles"]["TM-m30III"]


def test_calibration_codepage_candidates_for_tm_m30iii() -> None:
    """No CP858 candidate -- TM-m30III's index 19 is Unknown, not CP858."""
    profile_codepages = get_profile_codepages("TM-m30III")
    candidates = tuple(cp for cp in CODEPAGE_CANDIDATES if cp in profile_codepages)
    assert candidates == ("CP1252", "CP850", "CP437")


def test_registers_tm_m10_in_escpos_capabilities() -> None:
    """TRG-confirmed geometry; codepage table borrowed from TM-m30III."""
    register_custom_profiles()
    profile = escpos.capabilities.get_profile("TM-m10")
    assert profile.profile_data["media"]["width"]["pixels"] == 420
    assert profile.profile_data["fonts"]["0"]["columns"] == 35
    assert profile.profile_data["fonts"]["1"]["columns"] == 42
    assert profile.profile_data["fonts"]["2"]["columns"] == 46
    m30iii = escpos.capabilities.CAPABILITIES["profiles"]["TM-m30III"]
    assert profile.profile_data["codePages"] == m30iii["codePages"]
    # ...but a distinct dict: patching one table must not mutate the other.
    assert profile.profile_data["codePages"] is not m30iii["codePages"]


def test_registration_helpers_skip_when_template_profile_missing() -> None:
    """A degraded escpos database (e.g. its BrokenDefault fallback, which
    only carries "default") leaves each helper nothing to copy from --
    they must warn and skip, never raise or register partial data."""
    profiles: dict = {}
    _register_rp820(profiles)
    _register_tm_m30iii(profiles)
    _register_tm_m10(profiles)
    assert profiles == {}


def test_tm_m10_registration_is_idempotent() -> None:
    register_custom_profiles()
    register_custom_profiles()
    profile = escpos.capabilities.get_profile("TM-m10")
    assert profile.profile_data is escpos.capabilities.CAPABILITIES["profiles"]["TM-m10"]


def test_epson_tm_t70_aliases_resolve_to_tm_t88v() -> None:
    assert resolve_alias("Epson TM-T70") == "TM-T88V"
    assert resolve_alias("Epson TM-T70II") == "TM-T88V"


def test_epson_tm_m30_alias_resolves_to_tm_m30iii() -> None:
    assert resolve_alias("Epson TM-m30") == "TM-m30III"
