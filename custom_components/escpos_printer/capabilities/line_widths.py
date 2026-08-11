"""Line width capability functions."""

from __future__ import annotations

import logging

from .constants import COMMON_LINE_WIDTHS, PROFILE_AUTO, PROFILE_CUSTOM
from .loader import _get_capabilities

_LOGGER = logging.getLogger(__name__)

# A receipt printer never has fewer than 16 characters per line. Guards
# against upstream escpos-printer-db data bugs like NT-80-V-UL, whose
# fonts.columns values (9, 12) are actually font DOT widths mistakenly
# encoded as column counts (correct values: 48 and 64 on that profile).
_MIN_PLAUSIBLE_COLUMNS = 16


def get_profile_line_widths(profile_key: str | None) -> list[int]:
    """Get list of line widths (column counts) supported by a profile.

    Line widths are derived from the profile's font column definitions.

    Args:
        profile_key: Profile key, or empty/None for common widths.

    Returns:
        Sorted list of column widths from profile fonts.
    """
    if not profile_key or profile_key in (PROFILE_AUTO, PROFILE_CUSTOM):
        return COMMON_LINE_WIDTHS.copy()

    from .aliases import canonical_profile_key  # noqa: PLC0415

    profile_key = canonical_profile_key(profile_key)

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
            if isinstance(columns, int) and columns >= _MIN_PLAUSIBLE_COLUMNS:
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
