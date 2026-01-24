"""Feature and cut mode capability functions."""

from __future__ import annotations

from typing import Any

from .constants import DEFAULT_CUT_MODES, PROFILE_AUTO, PROFILE_CUSTOM
from .loader import _get_capabilities


def get_profile_cut_modes(profile_key: str | None) -> list[str]:
    """Get available cut modes for a profile based on its features.

    Args:
        profile_key: Profile key, or empty/None for default cut modes.

    Returns:
        List of available cut modes (always includes "none").
    """
    # Default: all cut modes available
    if not profile_key or profile_key in (PROFILE_AUTO, PROFILE_CUSTOM):
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


def profile_supports_feature(profile_key: str | None, feature: str) -> bool:
    """Check if a profile supports a specific feature.

    Args:
        profile_key: Profile key to check.
        feature: Feature name (e.g., 'qrCode', 'barcodeB', 'graphics').

    Returns:
        True if profile supports the feature, False otherwise.
    """
    if not profile_key or profile_key in (PROFILE_AUTO, PROFILE_CUSTOM):
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
    if not profile_key or profile_key in (PROFILE_AUTO, PROFILE_CUSTOM):
        return {}

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    if profile_key not in profiles:
        return {}

    profile = profiles[profile_key]
    features = profile.get("features", {})

    return {k: bool(v) for k, v in features.items() if isinstance(v, bool)}


def get_profile_info(profile_key: str | None) -> dict[str, Any]:
    """Get full profile information.

    Args:
        profile_key: Profile key to retrieve.

    Returns:
        Profile data dictionary, or empty dict if not found.
    """
    if not profile_key or profile_key in (PROFILE_AUTO, PROFILE_CUSTOM):
        return {}

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    result: dict[str, Any] = profiles.get(profile_key, {})
    return result
