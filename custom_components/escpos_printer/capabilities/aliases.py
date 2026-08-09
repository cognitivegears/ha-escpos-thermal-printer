"""Clone/equivalent-model aliases onto bundled escpos-printer-db profiles.

Aliases route rebadged or near-equivalent hardware to an existing
bundled profile. They only ever improve defaults (width, codepages) —
they never gate behavior. Genuinely new hardware belongs upstream in
escpos-printer-db, not here.

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
    # Misc verified 58mm/384dot ESC/POS clones.
    "HOIN HOP-E58": "POS-5890",
    "Goojprt PT-210": "POS-5890",
    "Netum NT-1809DD": "NT-5890K",
    # Sunmi: V1 same 58mm class as bundled Sunmi-V2; T2 built-in is
    # 80mm/576dots/203dpi per Sunmi docs.
    "Sunmi V1": "Sunmi-V2",
    "Sunmi T2": "NT-80-V-UL",
}


def _build_alias_table(models: dict[str, str]) -> dict[str, str]:
    """Normalize each display name into a full key AND a bare-model key
    (vendor word stripped), so both "Citizen CT-S601II" and bare
    "CT-S601II" resolve — the latter matters for the custom-profile field
    and for USB descriptors that omit the vendor name.
    """
    table: dict[str, str] = {}
    for display, target in models.items():
        keys = {normalize_model(display)}
        _vendor, _sep, rest = display.partition(" ")
        if rest:
            keys.add(normalize_model(rest))
        for key in keys:
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
