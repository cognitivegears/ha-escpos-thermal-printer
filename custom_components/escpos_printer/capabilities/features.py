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

    from .aliases import canonical_profile_key  # noqa: PLC0415

    profile_key = canonical_profile_key(profile_key)

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

    from .aliases import canonical_profile_key  # noqa: PLC0415

    profile_key = canonical_profile_key(profile_key)

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

    from .aliases import canonical_profile_key  # noqa: PLC0415

    profile_key = canonical_profile_key(profile_key)

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

    from .aliases import canonical_profile_key  # noqa: PLC0415

    profile_key = canonical_profile_key(profile_key)

    capabilities = _get_capabilities()
    profiles = capabilities.get("profiles", {})

    result: dict[str, Any] = profiles.get(profile_key, {})
    return result


# Preference order for automatic image implementation selection.
# graphics is deliberately absent: every bundled profile with graphics
# also declares bitImageRaster, so raster strictly dominates it for
# compatibility; graphics stays a manual choice.
_IMPL_PREFERENCE = ("bitImageRaster", "bitImageColumn")

_IMAGE_FEATURES = ("bitImageRaster", "bitImageColumn", "graphics")


def pick_impl(profile_key: str | None) -> str | None:
    """Pick the image implementation a profile declares support for.

    Returns None for auto/custom/unknown profiles (caller falls back to
    DEFAULT_IMPL) and for profiles that declare no image support at all
    (caller warns but still prints — feature flags are hints, not gates).
    """
    features = get_profile_features(profile_key)
    for impl in _IMPL_PREFERENCE:
        if features.get(impl):
            return impl
    return None


def profile_declares_no_images(profile_key: str | None) -> bool:
    """True when a known profile explicitly declares no image support."""
    features = get_profile_features(profile_key)
    if not features:
        return False  # auto/custom/unknown: assume capable, stay silent
    return not any(features.get(feature) for feature in _IMAGE_FEATURES)
