"""Codepage-related capability functions."""

from __future__ import annotations

import logging

from .constants import COMMON_CODEPAGES, OPTION_CUSTOM, PROFILE_AUTO, PROFILE_CUSTOM
from .loader import _get_capabilities

_LOGGER = logging.getLogger(__name__)


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
