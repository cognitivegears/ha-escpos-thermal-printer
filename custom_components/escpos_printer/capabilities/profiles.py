"""Profile-related capability functions."""

from __future__ import annotations

from .constants import PROFILE_AUTO, PROFILE_CUSTOM
from .loader import _get_capabilities


def get_profile_choices() -> list[tuple[str, str]]:
    """Get list of (profile_key, display_name) tuples for dropdown.

    Returns list sorted alphabetically with "Generic (no profile)" first
    and "Custom..." last.

    Returns:
        List of (key, display_name) tuples suitable for vol.In().
    """
    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    # Start with Auto-detect option
    choices: list[tuple[str, str]] = [(PROFILE_AUTO, "Generic (no profile)")]

    # Build profile list with vendor + name
    profile_list: list[tuple[str, str]] = []
    for key, profile_data in profiles.items():
        vendor = profile_data.get("vendor", "Generic")
        name = profile_data.get("name", key)
        display = f"{vendor} {name}" if vendor and vendor != "Generic" else name
        profile_list.append((key, display))

    from .aliases import ALIAS_MODELS, normalize_model  # noqa: PLC0415

    # Skip any alias whose normalized key collides with a real profile key.
    # A collision can show up in either derivation -- the full display name
    # ("Epson TM-T20III" -> "epsontmt20iii") or the bare model with the
    # vendor word stripped ("TM-T20III" -> "tmt20iii", matching how bundled
    # profile keys are usually spelled) -- so check both, mirroring
    # ``_build_alias_table``'s own key derivation.
    real_normalized = {normalize_model(key) for key in profiles}
    alias_list = []
    for display in ALIAS_MODELS:
        derived_keys = {normalize_model(display)}
        _vendor, _sep, rest = display.partition(" ")
        if rest:
            derived_keys.add(normalize_model(rest))
        if derived_keys & real_normalized:
            continue
        alias_list.append((normalize_model(display), f"{display} (compatible)"))

    # Single sort over the combined list so e.g. "Epson TM-T20III
    # (compatible)" sits next to "Epson TM-T20II".
    combined = profile_list + alias_list
    combined.sort(key=lambda x: x[1].lower())

    choices.extend(combined)

    # Add Custom option at the end
    choices.append((PROFILE_CUSTOM, "Custom (enter profile name)..."))

    return choices


def get_profile_choices_dict() -> dict[str, str]:
    """Get profile choices as a dictionary for vol.In().

    Returns:
        Dict mapping profile key to display name.
    """
    return dict(get_profile_choices())


def is_valid_profile(profile_key: str | None) -> bool:
    """Check if a profile key is valid.

    Args:
        profile_key: Profile key to validate.

    Returns:
        True if profile is valid (including a case variant or clone
        alias), empty (auto), or custom marker.
    """
    if not profile_key or profile_key == PROFILE_AUTO:
        return True  # Empty means auto
    if profile_key == PROFILE_CUSTOM:
        return True  # Custom marker is valid

    return resolve_profile_name(profile_key) is not None


def resolve_profile_name(raw: str | None) -> str | None:
    """Resolve user input to a bundled profile key.

    Accepts an exact key, a case-insensitive key, or a clone alias
    (see ``aliases.PROFILE_ALIASES``). Returns None when nothing matches.
    """
    if not raw:
        return None
    from .aliases import resolve_alias  # noqa: PLC0415

    raw = raw.strip()
    capabilities = _get_capabilities()
    profiles: dict[str, object] = capabilities.get("profiles", {})
    if raw in profiles:
        return raw
    lowered = {key.casefold(): key for key in profiles}
    if raw.casefold() in lowered:
        return lowered[raw.casefold()]
    target = resolve_alias(raw)
    if target and target in profiles:
        return target
    return None
