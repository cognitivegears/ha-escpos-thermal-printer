"""Text utilities for UTF-8 to codepage transcoding.

This package provides functions to transcode UTF-8 text to legacy codepages
used by ESC/POS thermal printers, with support for look-alike character
substitution when direct mapping is not available.

Character Mapping Strategy:
---------------------------
The transcoding process uses two fallback maps, applied in order ONLY when
direct encoding to the target codepage fails:

1. LOOKALIKE_MAP: ASCII fallbacks for characters that may or may not exist in
   the target codepage. Includes:
   - Universal lookalikes (curly quotes -> straight quotes, em dash -> --)
   - Box drawing/block elements (exist in CP437, fallback to ASCII for others)

2. ACCENT_FALLBACK_MAP: Fallbacks for accented characters and symbols that
   exist in some codepages but not others. Only used when direct encoding fails.

IMPORTANT: The transcode_to_codepage() function always tries direct encoding
first. Characters native to the target codepage (e.g., box drawing in CP437)
are preserved, not replaced with their ASCII fallbacks.
"""

from __future__ import annotations

# Re-export all public symbols for backward compatibility
from .accent_fallback_map import ACCENT_FALLBACK_MAP
from .codepage_mapping import CODEPAGE_TO_CODEC, get_codec_name
from .lookalike_map import LOOKALIKE_MAP
from .transcoding import (
    apply_accent_fallback,
    apply_lookalike_map,
    get_unmappable_chars,
    normalize_unicode,
    transcode_to_codepage,
)

__all__ = [
    "ACCENT_FALLBACK_MAP",
    "CODEPAGE_TO_CODEC",
    "LOOKALIKE_MAP",
    "apply_accent_fallback",
    "apply_lookalike_map",
    "get_codec_name",
    "get_unmappable_chars",
    "normalize_unicode",
    "transcode_to_codepage",
]
