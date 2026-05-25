"""Render a multi-column table with optional row separators and borders."""

from __future__ import annotations

from collections.abc import Sequence
import logging
import textwrap
import unicodedata

from .borders import BorderStyle, glyphs_for, resolve_style
from .width import pad_to_width, sanitize_layout_text

_LOGGER = logging.getLogger(__name__)

# Sample size for the wide-char probe (P-H2). A full per-cell scan over
# a worst-case 200x12x1000 ASCII table is ~100 ms of pure CPU on top of
# the ~310 ms textwrap pass. Sampling per cell keeps the warning
# diagnostic cheap.
_WIDE_CHAR_SAMPLE = 256

# Module-level guard so the wide-char warning fires at most once per
# Python process (Q-H2). HA surfaces WARNING via the Notifications panel.
# Wrapped in a single-element list so the per-call read/write is via
# ``__setitem__`` — see the analogous comment in ``box.py``.
_WARNED_WIDE_CHARS_TABLE: list[bool] = [False]


def _has_wide_chars(text: str) -> bool:
    """Return True if any of the first ``_WIDE_CHAR_SAMPLE`` chars is wide.

    These glyphs occupy two terminal columns but ``len()`` counts them
    as one — so the text-mode column padding silently misaligns.
    Sampling here keeps detection O(1) per cell; the renderer's output
    is functional even if the warning is missed.
    """
    return any(unicodedata.east_asian_width(c) in ("W", "F") for c in text[:_WIDE_CHAR_SAMPLE])


def _distribute_widths(total_width: int, n_cols: int, bordered: bool) -> list[int]:
    """Evenly distribute ``total_width`` across ``n_cols`` columns.

    For a bordered table the n_cols+1 vertical separators occupy one
    column each; for a borderless table only the n_cols-1 single-space
    inter-column gaps are subtracted. Negative results raise so the
    caller can surface a clear error instead of producing garbage rows.
    """
    if n_cols <= 0:
        raise ValueError(f"n_cols must be >= 1, got {n_cols}")
    separator_count = n_cols + 1 if bordered else max(0, n_cols - 1)
    usable = total_width - separator_count
    if usable < n_cols:
        raise ValueError(
            f"total_width={total_width} too small for {n_cols} columns "
            f"(need at least {n_cols + separator_count})"
        )
    base, extra = divmod(usable, n_cols)
    return [base + (1 if i < extra else 0) for i in range(n_cols)]


def _pad_cell(text: str, width: int, align: str) -> str:
    """Pad ``text`` (a single visual line) to ``width`` display columns."""
    return pad_to_width(text, width, align)


def _wrap_cell(text: str, width: int) -> list[str]:
    """Wrap a single cell's text into ``width``-column visual rows."""
    if width <= 0:
        return [""]
    lines: list[str] = []
    for source_line in str(text).splitlines() or [""]:
        if not source_line:
            lines.append("")
            continue
        wrapped = textwrap.wrap(
            source_line,
            width=width,
            replace_whitespace=False,
            drop_whitespace=False,
        )
        lines.extend(wrapped or [""])
    return lines or [""]


def _normalize_rows(rows: Sequence[Sequence[object]]) -> tuple[list[list[str]], int]:
    """Coerce every cell to ``str``, expand tabs, and right-pad short rows.

    Tab expansion happens here (rather than in the renderer) because the
    column-width math in :func:`_distribute_widths` assumes one cell
    string in, one cell value out — a bare ``\\t`` would print as eight
    columns on most printers while the width math saw one character.
    """
    if not rows:
        raise ValueError("rows must contain at least one row")
    n_cols = max(len(r) for r in rows)
    if n_cols < 1:
        raise ValueError("rows must contain at least one column")
    out: list[list[str]] = []
    for row in rows:
        cells = [sanitize_layout_text(str(c)) if c is not None else "" for c in row]
        if len(cells) < n_cols:
            cells.extend([""] * (n_cols - len(cells)))
        out.append(cells)
    return out, n_cols


def _build_row(
    cells: list[str],
    widths: list[int],
    aligns: list[str],
    style: BorderStyle,
) -> str:
    """Render one logical row (wraps each cell, pads to tallest sub-row)."""
    wrapped = [_wrap_cell(cell, w) for cell, w in zip(cells, widths, strict=True)]
    height = max(len(col) for col in wrapped)
    if style == "none":
        joiner = " "
    else:
        g = glyphs_for(style)
        joiner = g.v
    rendered_lines: list[str] = []
    for row_idx in range(height):
        parts = []
        for col_idx, col in enumerate(wrapped):
            line = col[row_idx] if row_idx < len(col) else ""
            parts.append(_pad_cell(line, widths[col_idx], aligns[col_idx]))
        if style == "none":
            rendered_lines.append(joiner.join(parts))
        else:
            rendered_lines.append(f"{joiner}{joiner.join(parts)}{joiner}")
    return "\n".join(rendered_lines)


def _build_separator(
    widths: list[int],
    style: BorderStyle,
    kind: str,
) -> str:
    """Build a top / bottom / inner separator line for the given style.

    ``kind`` is one of ``"top"``, ``"bottom"``, or ``"middle"``. Returns
    the empty string for ``style == "none"`` so the caller can skip it
    cleanly.
    """
    if style == "none":
        return ""
    g = glyphs_for(style)
    if kind == "top":
        left, joiner, right = g.tl, g.t_down, g.tr
    elif kind == "bottom":
        left, joiner, right = g.bl, g.t_up, g.br
    else:
        left, joiner, right = g.t_right, g.cross, g.t_left
    segments = [g.h * w for w in widths]
    return f"{left}{joiner.join(segments)}{right}"


def render_table(
    rows: Sequence[Sequence[object]],
    *,
    total_width: int,
    column_widths: Sequence[int] | None = None,
    column_aligns: Sequence[str] | None = None,
    style: BorderStyle | str = "auto",
    codepage: str | None = None,
    header: bool = False,
    row_separators: bool = False,
) -> str:
    """Render a list of rows as a multi-column block of text.

    ``total_width`` is the maximum printable width including any
    borders. ``column_widths`` overrides the even distribution; the sum
    of widths plus separators must not exceed ``total_width``. ``header``
    promotes the first row to a header (separated from the body by a
    horizontal rule). ``row_separators`` inserts a horizontal rule
    between every body row.
    """
    cells, n_cols = _normalize_rows(rows)
    if not _WARNED_WIDE_CHARS_TABLE[0] and any(
        _has_wide_chars(c) for row in cells for c in row
    ):
        _LOGGER.warning(
            "Table contains wide-width characters (CJK / fullwidth / emoji); "
            "column alignment may be off because text-mode padding assumes one "
            "column per character. Use print_text_image for accurate layout — "
            "see docs/text-effects.md#cjk. "
            "(This warning fires once per process.)"
        )
        _WARNED_WIDE_CHARS_TABLE[0] = True
    resolved = resolve_style(style, codepage)
    bordered = resolved != "none"

    if column_widths is None:
        widths = _distribute_widths(total_width, n_cols, bordered)
    else:
        widths = [int(w) for w in column_widths]
        if len(widths) != n_cols:
            raise ValueError(f"column_widths length {len(widths)} != column count {n_cols}")
        if any(w < 1 for w in widths):
            raise ValueError("every column width must be >= 1")
        separator_count = n_cols + 1 if bordered else max(0, n_cols - 1)
        if sum(widths) + separator_count > total_width:
            raise ValueError(
                f"column widths {widths} + {separator_count} separators "
                f"exceed total_width={total_width}"
            )

    if column_aligns is None:
        aligns = ["left"] * n_cols
    else:
        aligns = list(column_aligns)
        if len(aligns) != n_cols:
            raise ValueError(f"column_aligns length {len(aligns)} != column count {n_cols}")
        for a in aligns:
            if a not in ("left", "center", "right"):
                raise ValueError(f"column align must be left/center/right; got {a!r}")

    out_lines: list[str] = []
    top = _build_separator(widths, resolved, "top")
    if top:
        out_lines.append(top)

    body_start = 0
    if header and cells:
        out_lines.append(_build_row(cells[0], widths, aligns, resolved))
        mid = _build_separator(widths, resolved, "middle")
        if mid:
            out_lines.append(mid)
        body_start = 1

    for i, row in enumerate(cells[body_start:]):
        if row_separators and i > 0:
            mid = _build_separator(widths, resolved, "middle")
            if mid:
                out_lines.append(mid)
        out_lines.append(_build_row(row, widths, aligns, resolved))

    bottom = _build_separator(widths, resolved, "bottom")
    if bottom:
        out_lines.append(bottom)
    return "\n".join(out_lines)


__all__ = ["render_table"]
