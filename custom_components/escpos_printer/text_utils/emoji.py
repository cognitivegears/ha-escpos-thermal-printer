"""Find emoji in text so they can be drawn with a font instead of the codepage.

ESC/POS codepages hold no emoji, so the transcoder turns them into ``?``.
This module only *finds* them: :func:`split_runs` cuts a string into runs of
plain text and emoji, which the image renderer draws with the bundled Noto
Emoji font (see :mod:`..text_effects.font_render`).

What counts as an emoji:

* code points that default to emoji presentation (faces, animals, flags'
  regional indicators, ...), and
* text-style symbols (``♥``, ``©``, ``✔``, ...) only when followed by the
  emoji variation selector U+FE0F, so ordinary symbols a codepage can print
  natively stay text.

Multi-code-point sequences (skin tones, ZWJ families, keycaps, flags) are
kept together as one cluster. The monochrome font has no ligatures, so
:func:`render_form` shows a cluster as its component pictographs side by
side and drops the joiners and modifiers.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import re

ZWJ = 0x200D
VARIATION_SELECTOR_TEXT = 0xFE0E
VARIATION_SELECTOR_EMOJI = 0xFE0F
KEYCAP = 0x20E3

_SKIN_TONES = range(0x1F3FB, 0x1F400)
_REGIONAL_INDICATORS = range(0x1F1E6, 0x1F200)
_TAG_CHARACTERS = range(0xE0020, 0xE0080)

# Code points that are emoji on their own (Unicode ``Emoji_Presentation``).
_EMOJI_PRESENTATION: tuple[tuple[int, int], ...] = (
    (0x231A, 0x231B),
    (0x23E9, 0x23EC),
    (0x23F0, 0x23F0),
    (0x23F3, 0x23F3),
    (0x25FD, 0x25FE),
    (0x2614, 0x2615),
    (0x2648, 0x2653),
    (0x267F, 0x267F),
    (0x2693, 0x2693),
    (0x26A1, 0x26A1),
    (0x26AA, 0x26AB),
    (0x26BD, 0x26BE),
    (0x26C4, 0x26C5),
    (0x26CE, 0x26CE),
    (0x26D4, 0x26D4),
    (0x26EA, 0x26EA),
    (0x26F2, 0x26F3),
    (0x26F5, 0x26F5),
    (0x26FA, 0x26FA),
    (0x26FD, 0x26FD),
    (0x2705, 0x2705),
    (0x270A, 0x270B),
    (0x2728, 0x2728),
    (0x274C, 0x274C),
    (0x274E, 0x274E),
    (0x2753, 0x2755),
    (0x2757, 0x2757),
    (0x2795, 0x2797),
    (0x27B0, 0x27B0),
    (0x27BF, 0x27BF),
    (0x2B1B, 0x2B1C),
    (0x2B50, 0x2B50),
    (0x2B55, 0x2B55),
    (0x1F004, 0x1F004),
    (0x1F0CF, 0x1F0CF),
    (0x1F18E, 0x1F18E),
    (0x1F191, 0x1F19A),
    (0x1F1E6, 0x1F1FF),
    (0x1F201, 0x1F201),
    (0x1F21A, 0x1F21A),
    (0x1F22F, 0x1F22F),
    (0x1F232, 0x1F236),
    (0x1F238, 0x1F23A),
    (0x1F250, 0x1F251),
    (0x1F300, 0x1F320),
    (0x1F32D, 0x1F335),
    (0x1F337, 0x1F37C),
    (0x1F37E, 0x1F393),
    (0x1F3A0, 0x1F3CA),
    (0x1F3CF, 0x1F3D3),
    (0x1F3E0, 0x1F3F0),
    (0x1F3F4, 0x1F3F4),
    (0x1F3F8, 0x1F43E),
    (0x1F440, 0x1F440),
    (0x1F442, 0x1F4FC),
    (0x1F4FF, 0x1F53D),
    (0x1F54B, 0x1F54E),
    (0x1F550, 0x1F567),
    (0x1F57A, 0x1F57A),
    (0x1F595, 0x1F596),
    (0x1F5A4, 0x1F5A4),
    (0x1F5FB, 0x1F64F),
    (0x1F680, 0x1F6C5),
    (0x1F6CC, 0x1F6CC),
    (0x1F6D0, 0x1F6D2),
    (0x1F6D5, 0x1F6D7),
    (0x1F6DC, 0x1F6DF),
    (0x1F6EB, 0x1F6EC),
    (0x1F6F4, 0x1F6FC),
    (0x1F7E0, 0x1F7EB),
    (0x1F7F0, 0x1F7F0),
    (0x1F90C, 0x1F93A),
    (0x1F93C, 0x1F945),
    (0x1F947, 0x1F9FF),
    (0x1FA70, 0x1FA7C),
    (0x1FA80, 0x1FA89),
    (0x1FA8F, 0x1FAC6),
    (0x1FACE, 0x1FADC),
    (0x1FADF, 0x1FAE9),
    (0x1FAF0, 0x1FAF8),
)

# Code points that are text by default and become emoji with U+FE0F.
_TEXT_DEFAULT_EMOJI: tuple[tuple[int, int], ...] = (
    (0x23, 0x23),  # keycap bases # * 0-9
    (0x2A, 0x2A),
    (0x30, 0x39),
    (0xA9, 0xA9),
    (0xAE, 0xAE),
    (0x203C, 0x203C),
    (0x2049, 0x2049),
    (0x2122, 0x2122),
    (0x2139, 0x2139),
    (0x2194, 0x2199),
    (0x21A9, 0x21AA),
    (0x2328, 0x2328),
    (0x23CF, 0x23CF),
    (0x23ED, 0x23EF),
    (0x23F1, 0x23F2),
    (0x23F8, 0x23FA),
    (0x24C2, 0x24C2),
    (0x25AA, 0x25AB),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FC),
    (0x2600, 0x2604),
    (0x260E, 0x260E),
    (0x2611, 0x2611),
    (0x2618, 0x2618),
    (0x261D, 0x261D),
    (0x2620, 0x2620),
    (0x2622, 0x2623),
    (0x2626, 0x2626),
    (0x262A, 0x262A),
    (0x262E, 0x262F),
    (0x2638, 0x263A),
    (0x2640, 0x2640),
    (0x2642, 0x2642),
    (0x265F, 0x2660),
    (0x2663, 0x2663),
    (0x2665, 0x2666),
    (0x2668, 0x2668),
    (0x267B, 0x267B),
    (0x267E, 0x267E),
    (0x2692, 0x2692),
    (0x2694, 0x2697),
    (0x2699, 0x2699),
    (0x269B, 0x269C),
    (0x26A0, 0x26A0),
    (0x26A7, 0x26A7),
    (0x26B0, 0x26B1),
    (0x26C8, 0x26C8),
    (0x26CF, 0x26CF),
    (0x26D1, 0x26D1),
    (0x26D3, 0x26D3),
    (0x26E9, 0x26E9),
    (0x26F0, 0x26F1),
    (0x26F4, 0x26F4),
    (0x26F7, 0x26F9),
    (0x2702, 0x2702),
    (0x2708, 0x2709),
    (0x270C, 0x270D),
    (0x270F, 0x270F),
    (0x2712, 0x2712),
    (0x2714, 0x2714),
    (0x2716, 0x2716),
    (0x271D, 0x271D),
    (0x2721, 0x2721),
    (0x2733, 0x2734),
    (0x2744, 0x2744),
    (0x2747, 0x2747),
    (0x2763, 0x2764),
    (0x27A1, 0x27A1),
    (0x2934, 0x2935),
    (0x2B05, 0x2B07),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x1F170, 0x1F171),
    (0x1F17E, 0x1F17F),
    (0x1F202, 0x1F202),
    (0x1F237, 0x1F237),
    (0x1F321, 0x1F321),
    (0x1F324, 0x1F32C),
    (0x1F336, 0x1F336),
    (0x1F37D, 0x1F37D),
    (0x1F396, 0x1F397),
    (0x1F399, 0x1F39B),
    (0x1F39E, 0x1F39F),
    (0x1F3CB, 0x1F3CE),
    (0x1F3D4, 0x1F3DF),
    (0x1F3F3, 0x1F3F3),
    (0x1F3F5, 0x1F3F5),
    (0x1F3F7, 0x1F3F7),
    (0x1F43F, 0x1F43F),
    (0x1F441, 0x1F441),
    (0x1F4FD, 0x1F4FE),
    (0x1F549, 0x1F54A),
    (0x1F56F, 0x1F570),
    (0x1F573, 0x1F579),
    (0x1F587, 0x1F587),
    (0x1F58A, 0x1F58D),
    (0x1F590, 0x1F590),
    (0x1F5A5, 0x1F5A5),
    (0x1F5A8, 0x1F5A8),
    (0x1F5B1, 0x1F5B2),
    (0x1F5BC, 0x1F5BC),
    (0x1F5C2, 0x1F5C4),
    (0x1F5D1, 0x1F5D3),
    (0x1F5DC, 0x1F5DE),
    (0x1F5E1, 0x1F5E1),
    (0x1F5E3, 0x1F5E3),
    (0x1F5E8, 0x1F5E8),
    (0x1F5EF, 0x1F5EF),
    (0x1F5F3, 0x1F5F3),
    (0x1F5FA, 0x1F5FA),
    (0x1F6CB, 0x1F6CF),
    (0x1F6E0, 0x1F6E5),
    (0x1F6E9, 0x1F6E9),
    (0x1F6F0, 0x1F6F0),
    (0x1F6F3, 0x1F6F3),
)


def _in_ranges(code_point: int, ranges: tuple[tuple[int, int], ...]) -> bool:
    return any(low <= code_point <= high for low, high in ranges)


@lru_cache(maxsize=4096)
def _is_emoji_presentation(char: str) -> bool:
    return _in_ranges(ord(char), _EMOJI_PRESENTATION)


@lru_cache(maxsize=4096)
def _is_text_default_emoji(char: str) -> bool:
    return _in_ranges(ord(char), _TEXT_DEFAULT_EMOJI)


@dataclass(frozen=True, slots=True)
class TextRun:
    """A stretch of text that is either all emoji clusters or no emoji at all."""

    text: str
    emoji: bool


def _emoji_cluster_length(text: str, start: int) -> int:
    """Return how many characters of ``text[start:]`` form one emoji cluster, or 0."""
    length = len(text)
    char = text[start]
    code_point = ord(char)
    next_cp = ord(text[start + 1]) if start + 1 < length else 0

    if code_point in _REGIONAL_INDICATORS:
        # A flag is a pair of regional indicators; a lone one is still drawn.
        return 2 if next_cp in _REGIONAL_INDICATORS else 1

    if _is_emoji_presentation(char) or (
        _is_text_default_emoji(char) and next_cp in (VARIATION_SELECTOR_EMOJI, KEYCAP)
    ):
        index = start + 1
    else:
        return 0

    # Greedily absorb modifiers, joiners and the pictograph a joiner links to.
    while index < length:
        cp = ord(text[index])
        if cp in (VARIATION_SELECTOR_EMOJI, VARIATION_SELECTOR_TEXT, KEYCAP) or (
            cp in _SKIN_TONES or cp in _TAG_CHARACTERS
        ):
            index += 1
        elif cp == ZWJ and index + 1 < length and _starts_emoji(text[index + 1]):
            index += 2
        else:
            break
    return index - start


def _starts_emoji(char: str) -> bool:
    return _is_emoji_presentation(char) or _is_text_default_emoji(char)


def split_runs(text: str) -> list[TextRun]:
    """Cut ``text`` into alternating runs of plain text and emoji clusters."""
    runs: list[TextRun] = []
    buffer: list[str] = []
    emoji_buffer: list[str] = []
    index = 0
    while index < len(text):
        cluster_len = _emoji_cluster_length(text, index)
        if cluster_len:
            if buffer:
                runs.append(TextRun("".join(buffer), emoji=False))
                buffer = []
            emoji_buffer.append(text[index : index + cluster_len])
            index += cluster_len
            continue
        if emoji_buffer:
            runs.append(TextRun("".join(emoji_buffer), emoji=True))
            emoji_buffer = []
        buffer.append(text[index])
        index += 1
    if buffer:
        runs.append(TextRun("".join(buffer), emoji=False))
    if emoji_buffer:
        runs.append(TextRun("".join(emoji_buffer), emoji=True))
    return runs


def contains_emoji(text: str) -> bool:
    """Return True if ``text`` holds at least one emoji cluster."""
    return any(run.emoji for run in split_runs(text))


def render_form(emoji_run: str) -> str:
    """Reduce emoji clusters to the glyphs the monochrome font can draw.

    Skin-tone modifiers, variation selectors, tag characters and zero-width
    joiners are dropped; the pictographs of a joined sequence stay, so a
    "woman technologist" becomes woman + laptop.
    """
    return "".join(
        char
        for char in emoji_run
        if ord(char) not in _SKIN_TONES
        and ord(char) not in _TAG_CHARACTERS
        and ord(char) not in (ZWJ, VARIATION_SELECTOR_EMOJI, VARIATION_SELECTOR_TEXT)
    )


def strip_emoji(text: str) -> str:
    """Return ``text`` without emoji.

    Lines that lose an emoji also lose the space it leaves behind (double
    spaces and trailing spaces); untouched lines stay exactly as written.
    """
    cleaned_lines: list[str] = []
    for line in text.split("\n"):
        runs = split_runs(line)
        if not any(run.emoji for run in runs):
            cleaned_lines.append(line)
            continue
        kept = "".join(run.text for run in runs if not run.emoji)
        cleaned_lines.append(re.sub(r" {2,}", " ", kept).rstrip(" "))
    return "\n".join(cleaned_lines)


__all__ = [
    "TextRun",
    "contains_emoji",
    "render_form",
    "split_runs",
    "strip_emoji",
]
