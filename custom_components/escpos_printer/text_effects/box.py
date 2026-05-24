"""Render a single block of text wrapped in a printable border."""

from __future__ import annotations

import logging
import textwrap
import unicodedata

from .borders import BorderStyle, glyphs_for, resolve_style
from .width import pad_to_width, sanitize_layout_text

_LOGGER = logging.getLogger(__name__)


def _has_wide_chars(text: str) -> bool:
    """Return True if any character in ``text`` is East-Asian Wide or Fullwidth."""
    return any(unicodedata.east_asian_width(c) in ("W", "F") for c in text)


def _pad_line(line: str, width: int, align: str) -> str:
    """Pad ``line`` to ``width`` *display* columns honoring ``align``."""
    return pad_to_width(line, width, align)


def _wrap_lines(text: str, width: int) -> list[str]:
    """Wrap ``text`` to ``width`` columns, preserving blank input lines.

    ``textwrap`` counts code points, not display cells, so a wrapped
    line may still over-shoot ``width`` if it contains wide glyphs. The
    padder ultimately truncates such lines per :func:`pad_to_width`; the
    warning emitted by :func:`render_box` flags the misalignment for the
    user.
    """
    if width <= 0:
        return [text]
    out: list[str] = []
    for source_line in text.splitlines() or [""]:
        if not source_line:
            out.append("")
            continue
        wrapped = textwrap.wrap(
            source_line,
            width=width,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        if not wrapped:
            out.append("")
        else:
            out.extend(wrapped)
    return out


def render_box(
    text: str,
    *,
    inner_width: int,
    style: BorderStyle | str,
    codepage: str | None = None,
    padding: int = 0,
    align: str = "left",
) -> str:
    """Render ``text`` wrapped in a border ``inner_width + 2`` columns wide.

    ``style`` may be ``"auto"`` — it is resolved against ``codepage`` so
    callers can pass the printer codepage and get the right glyph family
    without branching. ``padding`` is the count of blank rows added above
    and below the content; horizontal padding is one space inside each
    side glyph plus ``padding`` extra spaces. The returned string has no
    trailing newline.
    """
    if inner_width < 1:
        raise ValueError(f"inner_width must be >= 1, got {inner_width}")
    if padding < 0:
        raise ValueError(f"padding must be >= 0, got {padding}")
    if align not in ("left", "center", "right"):
        raise ValueError(f"align must be left/center/right, got {align!r}")

    text = sanitize_layout_text(text)
    if _has_wide_chars(text):
        _LOGGER.warning(
            "Box content contains wide-width characters (CJK / fullwidth / "
            "emoji); the borders may misalign because textwrap wraps by "
            "code-point count, not display columns. Use print_text_image "
            "for accurate layout — see docs/text-effects.md#cjk."
        )
    resolved = resolve_style(style, codepage)
    if resolved == "none":
        wrapped = _wrap_lines(text, inner_width)
        return "\n".join(_pad_line(line, inner_width, align) for line in wrapped)

    g = glyphs_for(resolved)
    content_width = inner_width
    wrapped = _wrap_lines(text, content_width)

    horizontal = g.h * inner_width
    top = f"{g.tl}{horizontal}{g.tr}"
    bottom = f"{g.bl}{horizontal}{g.br}"
    blank = f"{g.v}{' ' * inner_width}{g.v}"

    rows: list[str] = [top]
    rows.extend(blank for _ in range(padding))
    rows.extend(f"{g.v}{_pad_line(line, content_width, align)}{g.v}" for line in wrapped)
    rows.extend(blank for _ in range(padding))
    rows.append(bottom)
    return "\n".join(rows)


__all__ = ["render_box"]
