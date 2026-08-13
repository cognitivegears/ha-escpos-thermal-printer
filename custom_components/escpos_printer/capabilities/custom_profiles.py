"""Register/patch printer profiles that escpos-printer-db gets wrong or lacks.

Unlike ``aliases.py`` (which points a display name at an *existing* bundled
profile), this module either builds genuinely new profile dicts (RP820,
TM-m30III) or corrects data in place (the clone-firmware codePages dedupe
below, and NT-80-V-UL's font columns) inside
``escpos.capabilities.CAPABILITIES["profiles"]`` so the fix applies
everywhere: the config-flow dropdown, the calibration codepage filter, and
the printer constructors (all of which resolve profile names through that
dict, either via our own loader or directly through
``escpos.capabilities.get_profile()``).
"""

from __future__ import annotations

import copy
import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Clone firmware (the whole reason these profiles get aliased to) only ever
# implements the standard Epson 0-47 ESC t table; indices at or above this
# are Epson's *extended* table, absent on clones.
_CLONE_TABLE_LIMIT = 48


def _dedupe_clone_codepages(profiles: dict[str, Any]) -> None:
    """Drop unreachable-on-clones duplicate codePages indices, in place.

    Several bundled profiles map one codepage name to two indices: a
    standard one and a duplicate >= 48 (escpos-printer-db's data entry
    bug, also reported upstream). ``BaseProfile.get_code_pages()`` inverts
    the dict last-wins, so python-escpos always emits whichever index
    comes last in iteration order -- on affected profiles that's the >=48
    duplicate, which doesn't exist in clone firmware's 0-47 table and
    garbles that codepage.

    Rule: for a name with multiple indices, drop the ones >= 48 *only if*
    a < 48 index also exists for that name. This is NOT the same as
    "lowest index always wins" -- some profiles (e.g. CT-S651) legitimately
    put their real, working index at 16 while a stale/inactive duplicate
    sits at 9; unconditionally keeping the lowest would regress those.
    Restricting the drop to the >=48 range only touches indices clone
    firmware can't reach anyway. "Unknown" placeholder entries are left
    untouched -- they're filtered out downstream (codepages.py) regardless
    of which index survives, so deduping them buys nothing and would make
    profiles with no *real* affected codepage (e.g. CT-S651) look changed.
    """
    for profile in profiles.values():
        code_pages: dict[str, str] = profile.get("codePages", {})
        indices_by_name: dict[str, list[int]] = {}
        for index_str, name in code_pages.items():
            if name == "Unknown":
                continue
            indices_by_name.setdefault(name, []).append(int(index_str))
        for indices in indices_by_name.values():
            low = [i for i in indices if i < _CLONE_TABLE_LIMIT]
            high = [i for i in indices if i >= _CLONE_TABLE_LIMIT]
            if low and high:
                for index in high:
                    del code_pages[str(index)]


def _patch_nt80vul_fonts(profiles: dict[str, Any]) -> None:
    """Correct NT-80-V-UL's font column counts, in place.

    fonts.columns holds glyph DOT widths (12, 9) mistakenly entered as
    column counts -- implausible for this 576px/80mm profile. Correct
    values: 576/12 = 48, 576/9 = 64 (also reported upstream to
    escpos-printer-db; drop this patch once the bundled DB ships fixed
    data). Guarded so a second call is a no-op.
    """
    profile = profiles.get("NT-80-V-UL")
    if profile is None:
        return
    fonts = profile.get("fonts", {})
    if fonts.get("0", {}).get("columns") == 12:
        fonts["0"]["columns"] = 48
    if fonts.get("1", {}).get("columns") == 9:
        fonts["1"]["columns"] = 64


def _register_rp820(profiles: dict[str, Any]) -> None:
    """Register the RP820 profile, a deep copy of TM-T20II with overrides.

    Idempotent: a no-op once already registered rather than rebinding a
    fresh dict -- escpos's ``get_profile_class`` caches the profile
    *class* keyed by name on first lookup, built from whichever dict was
    registered at that time, so a later call replacing the dict would
    leave the cached class pointing at stale data.
    """
    if "RP820" in profiles:
        return  # already registered; CLASS_CACHE pins the first dict, don't rebind it

    template = profiles.get("TM-T20II")
    if template is None:
        # Degraded python-escpos install (e.g. its BrokenDefault
        # fallback, which only has "default") -- nothing to copy from.
        _LOGGER.warning("TM-T20II profile not found, skipping RP820 registration")
        return

    # RP820: the Rongta RP850P announces itself on the network as
    # "RP820" (DHCP hostname Rongta_RP820, firmware GD207_v1.16). It
    # was previously aliased to the bundled NT-80-V-UL profile; even
    # after the codePages dedupe above, NT-80-V-UL still can't fully
    # replace this profile -- about 31 of its codepage names (CP1250,
    # CP1253, CP720, CP775, ...) only ever had a single index >= 48,
    # so they stay unreachable on clone firmware, whereas RP820's full
    # Epson table (copied from TM-T20II) covers them at their real
    # low indices. RP820 also carries hardware measurements NT-80-V-UL
    # doesn't have: per-DIP-mode geometry (below) and graphics=False.
    # This profile is a deep copy of the bundled TM-T20II profile
    # (same codePages/encodings) with media/fonts/features overridden
    # to match those measurements.
    #
    # Hardware-verified 2026-08-13 on a real RP850P unit: BOTH
    # geometries exist and follow the SW-5 column-mode DIP switch --
    # 48-column position: 576px raster / 48 text columns; 42-column
    # position: 512px raster / 42 text columns (each confirmed by a
    # fine-grained right-edge probe plus a text-column ruler in the
    # respective mode). All four calibration codepages
    # (CP858/CP1252/CP850/CP437) render correctly,
    # bitImageRaster/bitImageColumn print cleanly, graphics (GS ( L)
    # does not.
    rp820 = copy.deepcopy(template)
    rp820["name"] = "RP820"
    rp820["vendor"] = "Rongta"
    rp820["notes"] = (
        "Hardware-verified via the HA calibration wizard on a Rongta RP850P "
        "unit (firmware GD207_v1.16, which announces DHCP hostname "
        "Rongta_RP820). Defaults describe the 48-column SW-5 DIP position "
        "(576px/48 cols); the 42-column position is 512px/42 cols -- "
        "recalibrate after flipping the switch."
    )
    rp820["media"] = {"dpi": 203, "width": {"mm": 72, "pixels": 576}}
    rp820["features"] = {**rp820["features"], "graphics": False}
    # Defaults are the 48-column SW-5 position. media/fonts happen to
    # be value-identical to the TM-T20II template today, but they are
    # kept as explicit assignments on purpose: these numbers are our
    # own hardware measurements, not inheritances, and pinning them
    # means an upstream edit to TM-T20II's geometry can't silently
    # change RP820's. The 42-column position is 512px raster with
    # Font A 42 / Font B 56; users who flip SW-5 should recalibrate
    # (a calibration override wins over the profile default anyway).
    rp820["fonts"] = {
        "0": {"name": "Font A", "columns": 48},
        "1": {"name": "Font B", "columns": 64},
    }
    profiles["RP820"] = rp820


def _register_tm_m30iii(profiles: dict[str, Any]) -> None:
    """Register the Epson TM-m30III profile, verbatim from escpos-printer-db.

    Data carried from escpos-printer-db PR #93 (merged upstream,
    hardware-tested there) since it's absent from python-escpos 3.1's
    vendored database -- drop this once a python-escpos release ships it.
    The upstream YAML declares ``inherits: default`` for features/colors
    (no override), so those two keys are copied from the bundled
    "default" profile to match; everything else (fonts, media, codePages)
    is this printer's own data, transcribed as-is. Notably codePages
    index 19 is "Unknown", not CP858 -- unlike every other 80mm/576px
    profile in the bundled DB, which is why this is a standalone profile
    rather than an alias to one of them.

    Idempotent: a no-op once already registered, same reasoning as RP820.
    """
    if "TM-m30III" in profiles:
        return

    default = profiles.get("default")
    if default is None:
        _LOGGER.warning("default profile not found, skipping TM-m30III registration")
        return

    profiles["TM-m30III"] = {
        "name": "TM-m30III",
        "vendor": "Epson",
        "notes": (
            "Epson TM-m30III profile, carried from escpos-printer-db "
            "(PR #93). Tested with a TM-m30III (112) (SKU C31CK50112), "
            "the standard model, black, EU, without WiFi/Bluetooth "
            "support, using 80mm paper."
        ),
        "features": default["features"],
        "colors": default["colors"],
        "fonts": {
            "0": {"name": "Font A", "columns": 48},
            "1": {"name": "Font B", "columns": 57},
            "2": {"name": "Font C", "columns": 64},
        },
        "media": {"dpi": 203, "width": {"mm": 80, "pixels": 576}},
        "codePages": {
            "0": "CP437",
            "1": "CP932",
            "2": "CP850",
            "3": "CP860",
            "4": "CP863",
            "5": "CP865",
            "11": "Unknown",
            "12": "Unknown",
            "13": "CP857",
            "14": "CP737",
            "15": "ISO_8859-7",
            "16": "CP1252",
            "17": "CP866",
            "18": "CP852",
            "19": "Unknown",
            "20": "Unknown",
            "21": "CP874",
            "26": "Unknown",
            "30": "TCVN-3-1",
            "31": "TCVN-3-2",
            "32": "Unknown",
            "33": "CP775",
            "34": "CP855",
            "35": "CP861",
            "36": "CP862",
            "37": "CP864",
            "38": "CP869",
            "39": "ISO_8859-2",
            "40": "ISO_8859-15",
            "41": "Unknown",
            "42": "CP774",
            "43": "CP772",
            "44": "CP1125",
            "45": "CP1250",
            "46": "CP1251",
            "47": "CP1253",
            "48": "CP1254",
            "49": "CP1255",
            "50": "CP1256",
            "51": "CP1257",
            "52": "CP1258",
            "53": "RK1048",
            "255": "Unknown",
        },
    }


def register_custom_profiles() -> None:
    """Insert/patch our custom profiles in escpos's profile registry.

    Idempotent: the codePages/font patches no-op once already applied, and
    each registration helper below is a no-op once its profile already
    exists -- see each helper's docstring for why (in short: escpos's
    ``get_profile_class`` CLASS_CACHE pins the first dict it saw for a
    name). All patching runs inside one broad try/except: a malformed
    bundled profile (e.g. a non-numeric codePages key) must not crash
    integration import, mirroring ``loader._get_capabilities()``'s
    fallback philosophy.
    """
    try:
        from escpos.capabilities import CAPABILITIES  # noqa: PLC0415

        profiles: dict[str, Any] = CAPABILITIES["profiles"]

        _dedupe_clone_codepages(profiles)
        _patch_nt80vul_fonts(profiles)
        _register_rp820(profiles)
        _register_tm_m30iii(profiles)
    except Exception:  # mirror loader._get_capabilities's broad fallback
        _LOGGER.warning("Failed to register/patch custom printer profiles", exc_info=True)
