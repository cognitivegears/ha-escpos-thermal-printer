"""Border glyph tables and codepage-compatibility detection.

The ``single`` and ``double`` styles use Unicode box-drawing characters that
exist natively in cp437 / cp850 / cp852 / cp858 / cp860 / cp863 / cp865 /
cp866. When the configured printer codepage does not include them, the
``transcode_to_codepage`` lookalike map already substitutes ``+``, ``-``,
``|``, ``=`` so the printed layout still aligns column-for-column. The
``"auto"`` resolver picks ``single`` for codepages that support the
glyphs natively and falls back to ``ascii`` otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..text_utils import get_codec_name

BorderStyle = Literal["auto", "single", "double", "ascii", "asterisk", "hash", "none"]

# All concrete styles the renderer can emit. ``auto`` resolves to one of
# these; ``none`` is a renderer-side flag (no border characters at all).
BOX_STYLES: tuple[BorderStyle, ...] = (
    "auto",
    "single",
    "double",
    "ascii",
    "asterisk",
    "hash",
    "none",
)


@dataclass(frozen=True, slots=True)
class BorderGlyphs:
    """The eleven characters needed to draw a bordered grid.

    Field names are oriented as the user sees the page:

    ``tl/tr/bl/br``  — corners
    ``h``            — horizontal run (top/bottom + row separators)
    ``v``            — vertical run (left/right + column separators)
    ``t_down``       — top T (column separator meets top edge)
    ``t_up``         — bottom T (column separator meets bottom edge)
    ``t_right``      — left T (row separator meets left edge)
    ``t_left``       — right T (row separator meets right edge)
    ``cross``        — interior intersection
    """

    tl: str
    tr: str
    bl: str
    br: str
    h: str
    v: str
    t_down: str
    t_up: str
    t_right: str
    t_left: str
    cross: str


_SINGLE = BorderGlyphs(
    tl="┌",
    tr="┐",
    bl="└",
    br="┘",
    h="─",
    v="│",
    t_down="┬",
    t_up="┴",
    t_right="├",
    t_left="┤",
    cross="┼",
)

_DOUBLE = BorderGlyphs(
    tl="╔",
    tr="╗",
    bl="╚",
    br="╝",
    h="═",
    v="║",
    t_down="╦",
    t_up="╩",
    t_right="╠",
    t_left="╣",
    cross="╬",
)

_ASCII = BorderGlyphs(
    tl="+",
    tr="+",
    bl="+",
    br="+",
    h="-",
    v="|",
    t_down="+",
    t_up="+",
    t_right="+",
    t_left="+",
    cross="+",
)

_ASTERISK = BorderGlyphs(
    tl="*",
    tr="*",
    bl="*",
    br="*",
    h="*",
    v="*",
    t_down="*",
    t_up="*",
    t_right="*",
    t_left="*",
    cross="*",
)

_HASH = BorderGlyphs(
    tl="#",
    tr="#",
    bl="#",
    br="#",
    h="#",
    v="#",
    t_down="#",
    t_up="#",
    t_right="#",
    t_left="#",
    cross="#",
)

_GLYPHS: dict[str, BorderGlyphs] = {
    "single": _SINGLE,
    "double": _DOUBLE,
    "ascii": _ASCII,
    "asterisk": _ASTERISK,
    "hash": _HASH,
}

# Probe character used to decide whether a codepage supports the cp437
# box-drawing block. Picked from the ``single`` set so a successful
# encode for this char implies the rest of ``_SINGLE`` will encode too
# (they all live in the same 0xB3-0xDA range in cp437/850/852/etc.).
_PROBE_CHARS = (_SINGLE.h, _SINGLE.v, _SINGLE.tl, _DOUBLE.h)


def codepage_supports_box_drawing(codepage: str | None) -> bool:
    """Return True if ``codepage`` can encode cp437 box-drawing glyphs natively.

    Probes the actual Python codec rather than maintaining a hard-coded
    allowlist so new codecs (or library updates) are picked up
    automatically. ``codepage`` of ``None`` returns False — there is no
    configured codepage to encode into, so we conservatively fall back
    to ASCII glyphs.
    """
    if not codepage:
        return False
    try:
        codec_name = get_codec_name(codepage)
    except TypeError, ValueError, LookupError:
        return False
    try:
        for ch in _PROBE_CHARS:
            ch.encode(codec_name, errors="strict")
    except UnicodeEncodeError, LookupError:
        return False
    return True


def resolve_style(style: BorderStyle | str, codepage: str | None) -> BorderStyle:
    """Resolve the special ``"auto"`` style to a concrete style.

    Non-``auto`` styles pass through unchanged. ``auto`` picks ``single``
    when the printer codepage natively supports box-drawing characters,
    otherwise ``ascii``. The renderer treats both deterministically — the
    caller never sees ``auto``.
    """
    if style == "auto":
        return "single" if codepage_supports_box_drawing(codepage) else "ascii"
    if style not in BOX_STYLES:
        raise ValueError(f"Unknown border style {style!r}; expected one of {BOX_STYLES}")
    return style


def glyphs_for(style: BorderStyle | str) -> BorderGlyphs:
    """Return the glyph table for a concrete style.

    Raises :class:`ValueError` for ``"auto"`` (caller must resolve first)
    and ``"none"`` (no glyphs to return — caller should branch on the
    style instead).
    """
    if style in ("auto", "none"):
        raise ValueError(f"glyphs_for() requires a concrete style; got {style!r}")
    try:
        return _GLYPHS[str(style)]
    except KeyError as exc:
        raise ValueError(f"Unknown border style {style!r}") from exc


__all__ = [
    "BOX_STYLES",
    "BorderGlyphs",
    "BorderStyle",
    "codepage_supports_box_drawing",
    "glyphs_for",
    "resolve_style",
]
