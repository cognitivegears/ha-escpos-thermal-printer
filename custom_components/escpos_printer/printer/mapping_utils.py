"""Utility functions for value mapping in printer operations."""

from __future__ import annotations

from ..const import DEFAULT_ALIGN


def map_align(align: str | None) -> str:
    """Map alignment string to escpos alignment value."""
    if not align:
        return DEFAULT_ALIGN
    align = align.lower()
    return align if align in ("left", "center", "right") else DEFAULT_ALIGN


def map_underline(underline: str | None) -> int:
    """Map underline string to escpos underline value."""
    mapping = {"none": 0, "single": 1, "double": 2}
    if not underline:
        return 0
    return mapping.get(underline.lower(), 0)


def map_multiplier(val: str | int | None) -> int:
    """Map multiplier string or int to escpos multiplier value (1-8).

    Accepts named sizes ("normal", "double", "triple") or numeric values
    (int or numeric string). Values are clamped to the 1-8 range supported
    by python-escpos custom_size.
    """
    if val is None:
        return 1
    # Accept raw int (e.g. from YAML: width: 4)
    if isinstance(val, int):
        return max(1, min(8, val))
    mapping = {"normal": 1, "double": 2, "triple": 3}
    named = mapping.get(str(val).lower())
    if named is not None:
        return named
    # Accept numeric strings (e.g. "4")
    try:
        return max(1, min(8, int(val)))
    except (ValueError, TypeError):
        return 1


def map_cut(mode: str | None) -> str | None:
    """Map cut mode string to escpos cut value."""
    if not mode:
        return None
    mode_l = mode.lower()
    if mode_l == "partial":
        return "PART"
    if mode_l == "full":
        return "FULL"
    if mode_l == "none":
        return None
    return None
