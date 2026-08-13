"""Clone/equivalent-model aliases onto known printer profiles.

Aliases route rebadged or near-equivalent hardware to an existing
profile — almost always a bundled escpos-printer-db one, but occasionally
an integration-registered profile (see custom_profiles.py) when no bundled
profile's codepage table matches the hardware. They only ever improve
defaults (width, codepages) — they never gate behavior. Genuinely new
hardware belongs upstream in escpos-printer-db first; a custom profile is
the fallback only when upstream can't represent it (e.g. non-standard
codepage numbering).

Researched-but-held models (deliberately absent — conflicting or
unverified specs, or a widthless alias target): TM-m10/m30, TM-T70/T70II,
Rongta RP80/RP328, ZJ-8220, Bixolon SRP-350III, PeriPage/MTP-3, Citizen
CT-S801/851, generic Symcode/Bisofice. See the 2026-08-08 research in the
PR discussion.
"""

from __future__ import annotations

import re

_NORMALIZE_RE = re.compile(r"[^a-z0-9]+")


def normalize_model(name: str) -> str:
    """Lowercase and strip everything but letters/digits ("CT-S601 II" -> "cts601ii")."""
    return _NORMALIZE_RE.sub("", name.casefold())


# Display-name → bundled target profile. Source of truth for both the
# dropdown rows and the normalized alias lookup. Each group cites its basis.
ALIAS_MODELS: dict[str, str] = {
    # Citizen CT-S601/651 family: shared command reference
    # (escpos-printer-db issue #49), same 80mm/640px/203dpi class per
    # Citizen spec pages. S801/S851 excluded (576-vs-640 dot class unresolved).
    "Citizen CT-S601": "CT-S651",
    "Citizen CT-S601II": "CT-S651",
    "Citizen CT-S651II": "CT-S651",
    # Zjiang 5890 family: POS-5890 profile covers rebadges per its own notes.
    # ZJ-5802 verified 58mm/384dots/203dpi via FCC filing RVUZJ-5802DD.
    "Zjiang ZJ-5890": "POS-5890",
    "Zjiang ZJ-5890K": "POS-5890",
    "Zjiang POS-5890K": "POS-5890",
    "Zjiang ZJ-5802": "POS-5890",
    # Epson current-gen successors of TM-T20II: 80mm/576dots/203dpi per
    # Epson spec sheets (TM-T20III CPD-58120R1; TM-T82II/III brochures).
    "Epson TM-T20III": "TM-T20II",
    "Epson TM-T20X": "TM-T20II",
    "Epson TM-T82II": "TM-T20II",
    "Epson TM-T82III": "TM-T20II",
    # Epson TM-T88 successors: same 80mm/512dots/180dpi lineage as TM-T88V.
    "Epson TM-T88VI": "TM-T88V",
    "Epson TM-T88VII": "TM-T88V",
    # Xprinter: XP-58IIH 58mm/384dots (manuals.plus manual); XP-80C 80mm/576
    # (xprintertech.com); XP-N160II/XP-T80A 80mm/203dpi (vendor listings).
    "Xprinter XP-58IIH": "POS-5890",
    "Xprinter XP-80C": "NT-80-V-UL",
    "Xprinter XP-N160II": "NT-80-V-UL",
    "Xprinter XP-T80A": "NT-80-V-UL",
    # Rongta RP850P: hardware-verified on a real unit (self-test: 640-dot
    # head, GD207_v1.16 firmware). Raster width AND text columns follow
    # the DIP column-mode switch (SW-5): 576 dots / 48 columns in the
    # 48-column position, 512 dots / 42 columns in the 42-column position
    # (both modes probed on hardware 2026-08-13) — recalibrate after
    # flipping the switch. Over-width raster WRAPS onto extra lines rather
    # than clipping on this firmware. NOT aliased to RP326 because that
    # bundled profile declares no pixel width.
    #
    # Points at the custom "RP820" profile (registered in
    # custom_profiles.py), not a bundled escpos-printer-db profile.
    # It was previously aliased to NT-80-V-UL, but that profile's
    # codePages table sent ESC t 52/71/53 for CP437/CP1252/CP858, values
    # that don't exist in this firmware's 0-47 table, so every codepage
    # but CP850 printed garbage on real hardware -- the firmware actually
    # follows Epson's standard numbering (0/2/16/19 for the same four
    # codepages, hardware-verified 2026-08-13 via the HA calibration
    # wizard). custom_profiles.py now dedupes NT-80-V-UL's >=48 duplicate
    # indices at runtime too, so it *also* sends 0/2/16/19 for these four.
    # RP820 still earns its own profile: NT-80-V-UL's ~31 codepage names
    # that only ever had a single index >= 48 (e.g. CP1250, CP775) remain
    # unreachable on clone firmware, while RP820's full Epson table (copied
    # from TM-T20II) covers them at their real low indices; RP820 also
    # carries hardware-verified per-DIP-mode geometry (576px/48 cols in
    # the 48-column SW-5 position, 512px/42 cols in the 42-column one)
    # and graphics=False that NT-80-V-UL has no data for.
    #
    # "RP820" is also the DHCP hostname (Rongta_RP820) that RP850P hardware
    # announces on the network — observed on the hardware-verified unit
    # above. No separate "Rongta RP820" alias entry is needed: RP820 is now
    # a real profile key, so it already appears in the dropdown and
    # resolves directly without going through the alias table.
    "Rongta RP850P": "RP820",
    # Misc verified 58mm/384dot ESC/POS clones.
    "HOIN HOP-E58": "POS-5890",
    "Goojprt PT-210": "POS-5890",
    "Netum NT-1809DD": "NT-5890K",
    # Sunmi: V1 same 58mm class as bundled Sunmi-V2; T2 built-in is
    # 80mm/576dots/203dpi per Sunmi docs.
    "Sunmi V1": "Sunmi-V2",
    "Sunmi T2": "NT-80-V-UL",
}


def _alias_keys(display: str) -> tuple[str, ...]:
    """Normalize a display name into its full key AND its bare-model key
    (vendor word stripped) -- e.g. "Citizen CT-S601II" -> ("citizencts601ii",
    "cts601ii"). Both matter for resolution: the bare key covers the
    custom-profile field and USB descriptors that omit the vendor name;
    the bare key is also how real bundled profile keys are normalized, so
    it's what a collision check must compare against too.
    """
    _vendor, _sep, rest = display.partition(" ")
    if not rest:
        return (normalize_model(display),)
    return (normalize_model(display), normalize_model(rest))


def _build_alias_table(models: dict[str, str]) -> dict[str, str]:
    """Normalize each display name into its alias keys (see ``_alias_keys``)."""
    table: dict[str, str] = {}
    for display, target in models.items():
        for key in _alias_keys(display):
            table[key] = target
    return table


PROFILE_ALIASES: dict[str, str] = _build_alias_table(ALIAS_MODELS)


def resolve_alias(name: str) -> str | None:
    """Resolve a model name to a bundled profile key via the alias table."""
    return PROFILE_ALIASES.get(normalize_model(name))


def canonical_profile_key(profile_key: str | None) -> str | None:
    """Resolve an alias to its bundled target; pass through everything else."""
    if not profile_key:
        return profile_key
    from .profiles import resolve_profile_name  # noqa: PLC0415  (avoid cycle)

    return resolve_profile_name(profile_key) or profile_key
