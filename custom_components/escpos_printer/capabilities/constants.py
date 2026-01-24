"""Constants for ESC/POS printer capabilities."""

from __future__ import annotations

# Constants for special profile/option values
PROFILE_AUTO = ""  # Auto-detect (default) profile
PROFILE_CUSTOM = "__custom__"  # Custom profile option
OPTION_CUSTOM = "__custom__"  # Custom option for codepage/line_width

# Common fallback values (sorted for consistency)
COMMON_CODEPAGES = sorted(["CP437", "CP850", "CP852", "CP858", "CP1252", "ISO_8859-1"])
COMMON_LINE_WIDTHS = sorted([32, 42, 48, 56, 64, 72])
DEFAULT_CUT_MODES = ["none", "partial", "full"]  # Order matters: none first
