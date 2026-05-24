"""Display-width helpers for the text-mode layout renderers.

Thermal printers in text mode treat each printable byte as one column
cell. ``len()`` is wrong for CJK ideographs / fullwidth punctuation
(which occupy two cells), combining marks (zero cells), and control
characters (renderer-defined). :func:`display_width` returns the count
of cells a string consumes when printed in text mode, so the box and
table padders compute correct visual widths.

Negative ``wcswidth`` results (the library's "contains a non-printable
control character" sentinel) are treated as one column per char so the
caller never sees a confusing negative width — those characters should
have been stripped earlier by the security sanitiser.
"""

from __future__ import annotations

from wcwidth import wcswidth, wcwidth


def display_width(text: str) -> int:
    """Return the number of printer columns ``text`` will occupy.

    Wraps :func:`wcwidth.wcswidth` and coerces the ``-1`` sentinel to a
    safe per-character ``len()`` fallback so an unexpected control char
    cannot produce a negative width that later breaks ``"x" * width``.
    """
    measured: int = wcswidth(text)
    if measured >= 0:
        return measured
    return sum(max(0, wcwidth(c)) if wcwidth(c) >= 0 else 1 for c in text)


def pad_to_width(text: str, width: int, align: str) -> str:
    """Pad ``text`` to ``width`` *display* columns, honoring ``align``.

    Truncation falls back to per-character splitting because slicing by
    code units would split a fullwidth glyph in half visually (it would
    still consume two columns, overflowing the target).
    """
    current = display_width(text)
    if current >= width:
        return _truncate_to_width(text, width)
    pad = width - current
    if align == "right":
        return " " * pad + text
    if align == "center":
        left = pad // 2
        return " " * left + text + " " * (pad - left)
    return text + " " * pad


def _truncate_to_width(text: str, width: int) -> str:
    """Truncate ``text`` so it fits within ``width`` display columns."""
    if width <= 0:
        return ""
    if display_width(text) <= width:
        return text
    out: list[str] = []
    used = 0
    for ch in text:
        cw = wcwidth(ch)
        if cw < 0:
            cw = 1
        if used + cw > width:
            break
        out.append(ch)
        used += cw
    # If we stopped just shy of `width` (e.g. a wide glyph wouldn't fit
    # in the last column), pad the gap with a space so downstream code
    # that expects exact-width strings still gets one.
    if used < width:
        out.append(" " * (width - used))
    return "".join(out)


def sanitize_layout_text(text: str, *, tab_size: int = 4) -> str:
    """Normalise input that flows into the box/table renderers.

    - Expands ``\\t`` to ``tab_size`` spaces so tabs don't count as one
      column and print as eight on the device.
    - Strips bare ``\\r`` (CRLF survives ``splitlines()`` as ``\\n``).
    """
    if not text:
        return text
    return text.replace("\r\n", "\n").replace("\r", "\n").expandtabs(tab_size)


__all__ = ["display_width", "pad_to_width", "sanitize_layout_text"]
