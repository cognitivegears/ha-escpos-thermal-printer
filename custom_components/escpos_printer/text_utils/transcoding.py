"""Transcoding functions for UTF-8 to codepage conversion.

This module provides functions to transcode UTF-8 text to legacy codepages
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

import logging
import unicodedata

from .accent_fallback_map import ACCENT_FALLBACK_MAP
from .codepage_mapping import get_codec_name
from .lookalike_map import LOOKALIKE_MAP

_LOGGER = logging.getLogger(__name__)


def normalize_unicode(text: str) -> str:
    """Normalize Unicode text using NFKC normalization.

    NFKC normalization converts compatibility characters to their canonical
    equivalents (e.g., ligatures to separate characters, full-width to half-width).

    Args:
        text: Unicode text to normalize.

    Returns:
        Normalized text.
    """
    return unicodedata.normalize("NFKC", text)


def apply_lookalike_map(text: str) -> str:
    """Apply look-alike character substitution.

    Replaces Unicode characters with their ASCII look-alike equivalents.

    Args:
        text: Text to process.

    Returns:
        Text with look-alike substitutions applied.
    """
    result = []
    for char in text:
        if char in LOOKALIKE_MAP:
            result.append(LOOKALIKE_MAP[char])
        else:
            result.append(char)
    return "".join(result)


def apply_accent_fallback(text: str, codepage: str) -> str:
    """Apply accent fallback for characters not in target codepage.

    First tries to encode each character in the target codepage.
    If that fails, tries the accent fallback map.

    Args:
        text: Text to process.
        codepage: Target codepage name.

    Returns:
        Text with accent fallbacks applied where needed.
    """
    codec = get_codec_name(codepage)
    result = []

    for char in text:
        # Try to encode directly
        try:
            char.encode(codec)
            result.append(char)
        except (UnicodeEncodeError, LookupError):
            # Character not in codepage, try fallback
            if char in ACCENT_FALLBACK_MAP:
                result.append(ACCENT_FALLBACK_MAP[char])
            else:
                result.append(char)

    return "".join(result)


def transcode_to_codepage(
    text: str,
    codepage: str,
    replace_char: str = "?",
    apply_lookalikes: bool = True,
    apply_accents: bool = True,
) -> str:
    """Transcode UTF-8 text to a target codepage.

    This function performs intelligent character-by-character transcoding:
    1. NFKC Unicode normalization (compatibility decomposition)
    2. For each character:
       a. Try direct encoding to target codepage (preserves native chars like CP437 box drawing)
       b. If that fails, try look-alike substitution
       c. If that fails, try accent fallback
       d. If all fail, use replacement character

    This approach preserves characters native to the target codepage (e.g., box drawing
    and block characters in CP437) while still providing fallbacks for unsupported chars.

    Args:
        text: UTF-8 text to transcode.
        codepage: Target codepage name (e.g., "CP437", "ISO_8859-1").
        replace_char: Character to use for unmappable characters.
        apply_lookalikes: Whether to apply look-alike substitutions.
        apply_accents: Whether to apply accent fallbacks.

    Returns:
        Transcoded text as a string (decoded back from the codepage).
    """
    if not text:
        return text

    # Step 1: Normalize Unicode
    normalized = normalize_unicode(text)

    codec = get_codec_name(codepage)

    # Verify codec exists
    try:
        "".encode(codec)
    except LookupError:
        _LOGGER.warning("Unknown codepage '%s', using UTF-8", codepage)
        return normalized

    # Step 2: Process each character with smart fallback
    result_chars: list[str] = []

    for char in normalized:
        # Try direct encoding first (preserves native codepage characters)
        try:
            char.encode(codec)
            result_chars.append(char)
            continue
        except UnicodeEncodeError:
            pass  # Character not in codepage, try fallback maps below

        # Try look-alike substitution
        if apply_lookalikes and char in LOOKALIKE_MAP:
            replacement = LOOKALIKE_MAP[char]
            # Verify the replacement can be encoded
            try:
                replacement.encode(codec)
                result_chars.append(replacement)
                continue
            except UnicodeEncodeError:
                pass  # Lookalike also can't be encoded, try next fallback

        # Try accent fallback
        if apply_accents and char in ACCENT_FALLBACK_MAP:
            replacement = ACCENT_FALLBACK_MAP[char]
            try:
                replacement.encode(codec)
                result_chars.append(replacement)
                continue
            except UnicodeEncodeError:
                pass  # Fallback also can't be encoded

        # All fallbacks failed, use replacement character
        result_chars.append(replace_char)

    return "".join(result_chars)


def get_unmappable_chars(text: str, codepage: str) -> list[str]:
    """Get list of characters that cannot be mapped to the codepage.

    Useful for debugging or warning users about characters that will
    be replaced.

    Args:
        text: Text to check.
        codepage: Target codepage name.

    Returns:
        List of unique characters that cannot be mapped.
    """
    if not text:
        return []

    codec = get_codec_name(codepage)
    unmappable = []

    # Normalize first
    normalized = normalize_unicode(text)

    for char in normalized:
        if char in unmappable:
            continue
        try:
            char.encode(codec)
        except (UnicodeEncodeError, LookupError):
            # Check if it has a look-alike
            if char not in LOOKALIKE_MAP and char not in ACCENT_FALLBACK_MAP:
                unmappable.append(char)

    return unmappable
