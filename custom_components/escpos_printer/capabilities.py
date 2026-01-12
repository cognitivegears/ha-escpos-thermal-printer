"""
Capabilities module for ESC/POS Thermal Printer integration.

This module provides functions to interface with the python-escpos library's
capabilities database (escpos-printer-db) to dynamically retrieve printer
profiles, supported codepages, line widths, and cut modes.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

_LOGGER = logging.getLogger(__name__)

# Constants for special profile/option values
PROFILE_AUTO = ""  # Auto-detect (default) profile
PROFILE_CUSTOM = "__custom__"  # Custom profile option
OPTION_CUSTOM = "__custom__"  # Custom option for codepage/line_width

# Common fallback values (sorted for consistency)
COMMON_CODEPAGES = sorted(["CP437", "CP850", "CP852", "CP858", "CP1252", "ISO_8859-1"])
COMMON_LINE_WIDTHS = sorted([32, 42, 48, 56, 64, 72])
DEFAULT_CUT_MODES = ["none", "partial", "full"]  # Order matters: none first


@lru_cache(maxsize=1)
def _get_capabilities() -> dict[str, Any]:
    """Load capabilities from python-escpos (cached).

    Returns:
        Dictionary containing 'profiles' and 'encodings' data.
        Falls back to minimal capabilities if python-escpos unavailable.
    """
    try:
        from escpos.capabilities import CAPABILITIES

        return CAPABILITIES  # type: ignore[no-any-return]
    except ImportError:
        _LOGGER.warning("python-escpos capabilities not available, using fallback")
        return _get_fallback_capabilities()
    except Exception as e:
        _LOGGER.warning("Failed to load escpos capabilities: %s", e)
        return _get_fallback_capabilities()


def _get_fallback_capabilities() -> dict[str, Any]:
    """Return fallback capabilities when python-escpos is unavailable.

    Returns:
        Minimal capabilities dict with common profiles and encodings.
    """
    return {
        "profiles": {
            "default": {
                "name": "Default",
                "vendor": "Generic",
                "codePages": {"0": "CP437"},
                "fonts": {"0": {"name": "Font A", "columns": 48}},
                "features": {
                    "paperFullCut": True,
                    "paperPartCut": True,
                },
            }
        },
        "encodings": {
            "CP437": {"name": "CP437", "python_encode": "cp437"},
            "CP850": {"name": "CP850", "python_encode": "cp850"},
            "CP852": {"name": "CP852", "python_encode": "cp852"},
            "CP858": {"name": "CP858", "python_encode": "cp858"},
            "CP1252": {"name": "CP1252", "python_encode": "cp1252"},
            "ISO_8859-1": {"name": "ISO_8859-1", "python_encode": "iso-8859-1"},
        },
    }


# =============================================================================
# Profile Functions
# =============================================================================


def get_profile_choices() -> list[tuple[str, str]]:
    """Get list of (profile_key, display_name) tuples for dropdown.

    Returns list sorted alphabetically with "Auto-detect (Default)" first
    and "Custom..." last.

    Returns:
        List of (key, display_name) tuples suitable for vol.In().
    """
    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    # Start with Auto-detect option
    choices: list[tuple[str, str]] = [(PROFILE_AUTO, "Auto-detect (Default)")]

    # Build profile list with vendor + name
    profile_list: list[tuple[str, str]] = []
    for key, profile_data in profiles.items():
        vendor = profile_data.get("vendor", "Generic")
        name = profile_data.get("name", key)
        if vendor and vendor != "Generic":
            display = f"{vendor} {name}"
        else:
            display = name
        profile_list.append((key, display))

    # Sort by display name, case-insensitive
    profile_list.sort(key=lambda x: x[1].lower())

    choices.extend(profile_list)

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
        True if profile is valid, empty (auto), or custom marker.
    """
    if not profile_key or profile_key == PROFILE_AUTO:
        return True  # Empty means auto
    if profile_key == PROFILE_CUSTOM:
        return True  # Custom marker is valid

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})
    return profile_key in profiles


# =============================================================================
# Codepage Functions
# =============================================================================


def get_profile_codepages(profile_key: str | None) -> list[str]:
    """Get list of codepages supported by a profile.

    Args:
        profile_key: Profile key, or empty/None for common codepages.

    Returns:
        Sorted list of codepage names supported by the profile.
    """
    if not profile_key or profile_key == PROFILE_AUTO:
        return COMMON_CODEPAGES.copy()

    if profile_key == PROFILE_CUSTOM:
        # For custom profiles, return all available codepages
        return get_all_codepages()

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    if profile_key not in profiles:
        _LOGGER.debug("Unknown profile '%s', returning common codepages", profile_key)
        return COMMON_CODEPAGES.copy()

    profile = profiles[profile_key]
    code_pages = profile.get("codePages", {})

    # Get unique codepage names, filtering out "Unknown"
    unique_pages = set(code_pages.values())
    unique_pages.discard("Unknown")
    unique_pages.discard("")

    if not unique_pages:
        return COMMON_CODEPAGES.copy()

    return sorted(unique_pages)


def get_all_codepages() -> list[str]:
    """Get all available codepages from the library.

    Returns:
        Sorted list of all codepage names with python_encode support.
    """
    capabilities = _get_capabilities()
    encodings = capabilities.get("encodings", {})

    usable = [
        name
        for name, info in encodings.items()
        if isinstance(info, dict) and (info.get("python_encode") or info.get("iconv"))
    ]

    return sorted(usable) if usable else COMMON_CODEPAGES.copy()


def is_valid_codepage_for_profile(codepage: str | None, profile_key: str | None) -> bool:
    """Check if codepage is valid for the given profile.

    Args:
        codepage: Codepage to validate.
        profile_key: Profile to check against.

    Returns:
        True if codepage is valid for the profile, or if codepage is empty.
    """
    if not codepage:
        return True

    if codepage == OPTION_CUSTOM:
        return True  # Custom marker is valid

    if not profile_key or profile_key == PROFILE_AUTO:
        # For auto profile, accept any known codepage
        return codepage in get_all_codepages() or codepage in COMMON_CODEPAGES

    supported = get_profile_codepages(profile_key)
    return codepage in supported or codepage in COMMON_CODEPAGES


# =============================================================================
# Line Width Functions
# =============================================================================


def get_profile_line_widths(profile_key: str | None) -> list[int]:
    """Get list of line widths (column counts) supported by a profile.

    Line widths are derived from the profile's font column definitions.

    Args:
        profile_key: Profile key, or empty/None for common widths.

    Returns:
        Sorted list of column widths from profile fonts.
    """
    if not profile_key or profile_key == PROFILE_AUTO or profile_key == PROFILE_CUSTOM:
        return COMMON_LINE_WIDTHS.copy()

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    if profile_key not in profiles:
        _LOGGER.debug("Unknown profile '%s', returning common line widths", profile_key)
        return COMMON_LINE_WIDTHS.copy()

    profile = profiles[profile_key]
    fonts = profile.get("fonts", {})

    # Extract column counts from all fonts
    widths: set[int] = set()
    for font_data in fonts.values():
        if isinstance(font_data, dict):
            columns = font_data.get("columns")
            if isinstance(columns, int) and columns > 0:
                widths.add(columns)

    if not widths:
        return COMMON_LINE_WIDTHS.copy()

    return sorted(widths)


def get_all_line_widths() -> list[int]:
    """Get all common line widths.

    Returns:
        List of common column widths.
    """
    return COMMON_LINE_WIDTHS.copy()


# =============================================================================
# Cut Mode Functions
# =============================================================================


def get_profile_cut_modes(profile_key: str | None) -> list[str]:
    """Get available cut modes for a profile based on its features.

    Args:
        profile_key: Profile key, or empty/None for default cut modes.

    Returns:
        List of available cut modes (always includes "none").
    """
    # Default: all cut modes available
    if not profile_key or profile_key == PROFILE_AUTO or profile_key == PROFILE_CUSTOM:
        return DEFAULT_CUT_MODES.copy()

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    if profile_key not in profiles:
        return DEFAULT_CUT_MODES.copy()

    profile = profiles[profile_key]
    features = profile.get("features", {})

    modes = ["none"]  # Always include "none"

    if features.get("paperPartCut"):
        modes.append("partial")

    if features.get("paperFullCut"):
        modes.append("full")

    return modes


# =============================================================================
# Feature Query Functions
# =============================================================================


def profile_supports_feature(profile_key: str | None, feature: str) -> bool:
    """Check if a profile supports a specific feature.

    Args:
        profile_key: Profile key to check.
        feature: Feature name (e.g., 'qrCode', 'barcodeB', 'graphics').

    Returns:
        True if profile supports the feature, False otherwise.
    """
    if not profile_key or profile_key == PROFILE_AUTO or profile_key == PROFILE_CUSTOM:
        # For auto/custom profiles, assume all features available
        return True

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    if profile_key not in profiles:
        return True  # Unknown profiles assume feature support

    profile = profiles[profile_key]
    features = profile.get("features", {})

    return bool(features.get(feature, False))


def get_profile_features(profile_key: str | None) -> dict[str, bool]:
    """Get all features for a profile.

    Args:
        profile_key: Profile key to check.

    Returns:
        Dictionary of feature names to boolean support values.
    """
    if not profile_key or profile_key == PROFILE_AUTO or profile_key == PROFILE_CUSTOM:
        return {}

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    if profile_key not in profiles:
        return {}

    profile = profiles[profile_key]
    features = profile.get("features", {})

    return {k: bool(v) for k, v in features.items() if isinstance(v, bool)}


# =============================================================================
# Utility Functions
# =============================================================================


def get_profile_info(profile_key: str | None) -> dict[str, Any]:
    """Get full profile information.

    Args:
        profile_key: Profile key to retrieve.

    Returns:
        Profile data dictionary, or empty dict if not found.
    """
    if not profile_key or profile_key == PROFILE_AUTO or profile_key == PROFILE_CUSTOM:
        return {}

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    result: dict[str, Any] = profiles.get(profile_key, {})
    return result


def clear_capabilities_cache() -> None:
    """Clear the capabilities cache.

    Useful for testing or when capabilities file changes.
    """
    _get_capabilities.cache_clear()
