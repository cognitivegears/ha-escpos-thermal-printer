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


def map_multiplier(val: str | None) -> int:
    """Map multiplier string to escpos multiplier value."""
    mapping = {"normal": 1, "double": 2, "triple": 3}
    if not val:
        return 1
    return mapping.get(val.lower(), 1)


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
