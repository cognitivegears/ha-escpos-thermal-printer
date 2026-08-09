"""Tests for clone alias table and profile name resolution."""

from custom_components.escpos_printer.capabilities.aliases import (
    PROFILE_ALIASES,
    normalize_model,
    resolve_alias,
)
from custom_components.escpos_printer.capabilities.loader import _get_capabilities
from custom_components.escpos_printer.capabilities.profiles import resolve_profile_name


def test_normalize_model() -> None:
    assert normalize_model("CT-S601 II") == "cts601ii"
    assert normalize_model("ZJ_5890-K") == "zj5890k"


def test_every_alias_target_exists_in_bundled_db() -> None:
    profiles = _get_capabilities()["profiles"]
    for alias, target in PROFILE_ALIASES.items():
        assert alias == normalize_model(alias), f"alias key {alias!r} must be pre-normalized"
        assert target in profiles, f"alias {alias!r} -> {target!r} not in bundled DB"


def test_resolve_alias() -> None:
    assert resolve_alias("CT-S601II") == "CT-S651"
    assert resolve_alias("nonsense-model") is None


def test_resolve_profile_name() -> None:
    assert resolve_profile_name("TM-T20II") == "TM-T20II"  # exact
    assert resolve_profile_name("tm-t20ii") == "TM-T20II"  # case-insensitive
    assert resolve_profile_name("CT-S601II") == "CT-S651"  # alias
    assert resolve_profile_name("no-such-printer") is None
    assert resolve_profile_name("") is None
    assert resolve_profile_name(None) is None
