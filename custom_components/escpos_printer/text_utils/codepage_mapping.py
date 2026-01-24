"""Codepage to Python codec mapping.

This module provides the CODEPAGE_TO_CODEC dictionary and get_codec_name function
for converting codepage names to Python codec names.
"""

from __future__ import annotations

# Mapping from common codepage names to Python codec names
CODEPAGE_TO_CODEC: dict[str, str] = {
    "CP437": "cp437",
    "CP850": "cp850",
    "CP852": "cp852",
    "CP858": "cp858",
    "CP860": "cp860",
    "CP863": "cp863",
    "CP865": "cp865",
    "CP866": "cp866",
    "CP932": "cp932",
    "CP1250": "cp1250",
    "CP1251": "cp1251",
    "CP1252": "cp1252",
    "CP1253": "cp1253",
    "CP1254": "cp1254",
    "CP1255": "cp1255",
    "CP1256": "cp1256",
    "CP1257": "cp1257",
    "CP1258": "cp1258",
    "ISO_8859-1": "iso-8859-1",
    "ISO_8859-2": "iso-8859-2",
    "ISO_8859-7": "iso-8859-7",
    "ISO_8859-15": "iso-8859-15",
    "LATIN1": "latin-1",
    "UTF-8": "utf-8",
}


def get_codec_name(codepage: str) -> str:
    """Get Python codec name for a codepage.

    Args:
        codepage: Codepage name (e.g., "CP437", "ISO_8859-1").

    Returns:
        Python codec name.
    """
    # Check mapping first
    if codepage.upper() in CODEPAGE_TO_CODEC:
        return CODEPAGE_TO_CODEC[codepage.upper()]

    # Try common transformations
    normalized = codepage.upper().replace("-", "_").replace(" ", "")

    # Handle CP prefix
    if normalized.startswith("CP") and normalized[2:].isdigit():
        return f"cp{normalized[2:]}"

    # Handle ISO_8859 prefix
    if normalized.startswith("ISO_8859_") or normalized.startswith("ISO8859_"):
        num = normalized.split("_")[-1]
        return f"iso-8859-{num}"

    # Fall back to lowercase
    return codepage.lower()
