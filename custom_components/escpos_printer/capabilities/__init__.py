"""Capabilities module for ESC/POS Thermal Printer integration.

This module provides functions to interface with the python-escpos library's
capabilities database (escpos-printer-db) to dynamically retrieve printer
profiles, supported codepages, line widths, and cut modes.
"""

from __future__ import annotations

from .codepages import (
    get_all_codepages,
    get_profile_codepages,
    is_valid_codepage_for_profile,
)
from .constants import (
    COMMON_CODEPAGES,
    COMMON_LINE_WIDTHS,
    DEFAULT_CUT_MODES,
    OPTION_CUSTOM,
    PROFILE_AUTO,
    PROFILE_CUSTOM,
)
from .features import (
    get_profile_cut_modes,
    get_profile_features,
    get_profile_info,
    profile_supports_feature,
)
from .line_widths import get_all_line_widths, get_profile_line_widths
from .loader import clear_capabilities_cache
from .profiles import get_profile_choices, get_profile_choices_dict, is_valid_profile

__all__ = [
    "COMMON_CODEPAGES",
    "COMMON_LINE_WIDTHS",
    "DEFAULT_CUT_MODES",
    "OPTION_CUSTOM",
    "PROFILE_AUTO",
    "PROFILE_CUSTOM",
    "clear_capabilities_cache",
    "get_all_codepages",
    "get_all_line_widths",
    "get_profile_choices",
    "get_profile_choices_dict",
    "get_profile_codepages",
    "get_profile_cut_modes",
    "get_profile_features",
    "get_profile_info",
    "get_profile_line_widths",
    "is_valid_codepage_for_profile",
    "is_valid_profile",
    "profile_supports_feature",
]
