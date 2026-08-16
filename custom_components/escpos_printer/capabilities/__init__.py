"""Capabilities module for ESC/POS Thermal Printer integration.

This module provides functions to interface with the python-escpos library's
capabilities database (escpos-printer-db) to dynamically retrieve printer
profiles, supported codepages, line widths, and cut modes.
"""

from __future__ import annotations

from .aliases import PROFILE_ALIASES, canonical_profile_key, normalize_model, resolve_alias
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
from .custom_profiles import register_custom_profiles
from .features import (
    get_profile_cut_modes,
    get_profile_features,
    get_profile_info,
    pick_impl,
    profile_declares_no_images,
    profile_provides_calibration,
    profile_supports_feature,
)
from .line_widths import get_all_line_widths, get_profile_line_widths
from .loader import clear_capabilities_cache
from .profiles import (
    get_profile_choices,
    get_profile_choices_dict,
    is_valid_profile,
    resolve_profile_name,
)
from .suggestions import suggest_profile

# Register hardware-verified profiles that aren't in escpos-printer-db yet.
# Runs at import time (rather than lazily on first capabilities lookup) so
# it's guaranteed to happen before *every* consumer: this package is always
# imported by the integration's top-level ``__init__.py`` before
# ``async_setup_entry`` runs, and before ``printer/base_adapter.py`` (which
# calls ``escpos.capabilities.get_profile()`` directly, bypassing our own
# loader) can be reached -- Python always finishes initializing a parent
# package before any of its submodules execute.
register_custom_profiles()

__all__ = [
    "COMMON_CODEPAGES",
    "COMMON_LINE_WIDTHS",
    "DEFAULT_CUT_MODES",
    "OPTION_CUSTOM",
    "PROFILE_ALIASES",
    "PROFILE_AUTO",
    "PROFILE_CUSTOM",
    "canonical_profile_key",
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
    "normalize_model",
    "pick_impl",
    "profile_declares_no_images",
    "profile_provides_calibration",
    "profile_supports_feature",
    "register_custom_profiles",
    "resolve_alias",
    "resolve_profile_name",
    "suggest_profile",
]
