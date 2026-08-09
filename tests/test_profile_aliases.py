"""Tests for clone alias table and profile name resolution."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.capabilities.aliases import (
    ALIAS_MODELS,
    PROFILE_ALIASES,
    canonical_profile_key,
    normalize_model,
    resolve_alias,
)
from custom_components.escpos_printer.capabilities.codepages import get_profile_codepages
from custom_components.escpos_printer.capabilities.features import pick_impl
from custom_components.escpos_printer.capabilities.loader import _get_capabilities
from custom_components.escpos_printer.capabilities.profiles import (
    get_profile_choices,
    resolve_profile_name,
)
from custom_components.escpos_printer.const import CONF_PROFILE, DOMAIN


def test_normalize_model() -> None:
    assert normalize_model("CT-S601 II") == "cts601ii"
    assert normalize_model("ZJ_5890-K") == "zj5890k"


def test_every_alias_target_exists_in_bundled_db() -> None:
    profiles = _get_capabilities()["profiles"]
    for alias, target in PROFILE_ALIASES.items():
        assert alias == normalize_model(alias), f"alias key {alias!r} must be pre-normalized"
        assert target in profiles, f"alias {alias!r} -> {target!r} not in bundled DB"


def test_every_alias_target_declares_a_pixel_width() -> None:
    """The whole point of an alias is supplying width; widthless targets fail."""
    profiles = _get_capabilities()["profiles"]
    for alias, target in PROFILE_ALIASES.items():
        width = profiles[target].get("media", {}).get("width", {}).get("pixels")
        assert isinstance(width, (int, float)), f"alias {alias!r} -> {target!r} has no pixel width"


def test_no_display_name_normalization_collisions() -> None:
    """No derived key (full display name or bare vendor-stripped model)
    may map to two different targets."""
    derived: dict[str, str] = {}
    for display, target in ALIAS_MODELS.items():
        keys = {normalize_model(display)}
        _vendor, _sep, rest = display.partition(" ")
        if rest:
            keys.add(normalize_model(rest))
        for key in keys:
            assert key not in derived or derived[key] == target, (
                f"derived key {key!r} maps to both {derived.get(key)!r} and {target!r}"
            )
            derived[key] = target
    assert derived == PROFILE_ALIASES


def test_bare_model_keys_also_resolve() -> None:
    """A key with the vendor word stripped must resolve too (custom-profile
    field entry, and USB descriptors that omit the vendor name)."""
    assert PROFILE_ALIASES["cts601ii"] == "CT-S651"
    assert PROFILE_ALIASES["zj5890"] == "POS-5890"
    assert PROFILE_ALIASES["tmt20iii"] == "TM-T20II"
    assert PROFILE_ALIASES["v1"] == "Sunmi-V2"


def test_no_alias_collides_with_a_real_profile_key() -> None:
    profiles = _get_capabilities()["profiles"]
    real_normalized = {normalize_model(key) for key in profiles}
    for alias in PROFILE_ALIASES:
        assert alias not in real_normalized, f"alias key {alias!r} collides with a real profile"


def test_expanded_alias_count() -> None:
    # Lower bound only — the invariant tests above pin the properties that
    # matter; an exact count would just churn on every addition.
    assert len(ALIAS_MODELS) >= 22


def test_resolve_alias() -> None:
    # Both the bare model name and the vendor-prefixed display name resolve.
    assert resolve_alias("CT-S601II") == "CT-S651"
    assert resolve_alias("Citizen CT-S601II") == "CT-S651"
    assert resolve_alias("Epson TM-T20III") == "TM-T20II"
    assert resolve_alias("nonsense-model") is None


def test_resolve_profile_name() -> None:
    assert resolve_profile_name("TM-T20II") == "TM-T20II"  # exact
    assert resolve_profile_name("tm-t20ii") == "TM-T20II"  # case-insensitive
    assert resolve_profile_name("CT-S601II") == "CT-S651"  # bare-model alias
    assert resolve_profile_name("Citizen CT-S601II") == "CT-S651"  # vendor-prefixed alias
    assert resolve_profile_name("no-such-printer") is None
    assert resolve_profile_name("") is None
    assert resolve_profile_name(None) is None


def test_canonical_profile_key() -> None:
    assert canonical_profile_key(normalize_model("Epson TM-T88VI")) == "TM-T88V"
    assert canonical_profile_key("TM-T20II") == "TM-T20II"  # already canonical, passes through
    assert canonical_profile_key("no-such-printer") == "no-such-printer"  # unknown, passthrough
    assert canonical_profile_key(None) is None
    assert canonical_profile_key("") == ""


def test_dropdown_includes_alias_rows() -> None:
    choices = get_profile_choices()
    assert ("epsontmt20iii", "Epson TM-T20III (compatible)") in choices
    assert choices[0][1] == "Generic (no profile)"
    assert choices[-1][1] == "Custom (enter profile name)..."


def test_dropdown_stays_sorted_with_aliases_merged_in() -> None:
    choices = get_profile_choices()
    middle = choices[1:-1]
    display_names = [v for _k, v in middle]
    assert display_names == sorted(display_names, key=str.lower)


def test_codepages_canonicalize_alias_key() -> None:
    alias_key = normalize_model("Xprinter XP-80C")
    assert get_profile_codepages(alias_key) == get_profile_codepages("NT-80-V-UL")


def test_pick_impl_canonicalizes_alias_key() -> None:
    alias_key = normalize_model("Epson TM-T88VI")
    assert pick_impl(alias_key) == pick_impl("TM-T88V")


async def test_setup_entry_resolves_alias_to_target_profile(hass) -> None:  # type: ignore[no-untyped-def]
    """A config entry whose stored profile is an alias key must end up with
    an adapter configured for the bundled TARGET profile, not the alias key.
    """
    alias_key = normalize_model("Xprinter XP-80C")  # -> NT-80-V-UL, 576px
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100, CONF_PROFILE: alias_key},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    adapter = entry.runtime_data.adapter
    assert adapter._config.profile == "NT-80-V-UL"
    assert adapter.get_profile_pixel_width() == 576
