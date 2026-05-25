"""Direct unit tests for ``text_effects.width``.

The box / table renderers exercise the happy path indirectly, but the
defensive branches (control-char fallback, zero/negative widths, the
trailing-space pad after a wide-glyph truncation, the empty-text early
return in :func:`sanitize_layout_text`) are not reached through any
end-to-end test. These tests target each branch explicitly.
"""

from __future__ import annotations

from custom_components.escpos_printer.text_effects.width import (
    _truncate_to_width,
    display_width,
    pad_to_width,
    sanitize_layout_text,
)


def test_display_width_basic_ascii() -> None:
    assert display_width("hello") == 5


def test_display_width_fullwidth_cjk_is_two_columns_per_glyph() -> None:
    # Each CJK ideograph occupies 2 cells in text mode.
    assert display_width("漢字") == 4


def test_display_width_control_char_falls_back_to_one_column() -> None:
    # ``wcswidth`` returns -1 when the string contains a control char;
    # the function should not propagate that negative width.
    result = display_width("a\x01b")
    assert result >= 0
    # ``\x01`` counted as one (the fallback) plus the two printable chars.
    assert result == 3


def test_pad_to_width_left_align_pads_right() -> None:
    assert pad_to_width("hi", 5, "left") == "hi   "


def test_pad_to_width_right_align_pads_left() -> None:
    assert pad_to_width("hi", 5, "right") == "   hi"


def test_pad_to_width_center_align_balances_padding() -> None:
    # 5 - 2 = 3 padding. left = 3//2 = 1, right = 3 - 1 = 2.
    assert pad_to_width("hi", 5, "center") == " hi  "


def test_pad_to_width_already_full_truncates() -> None:
    assert pad_to_width("hello world", 5, "left") == "hello"


def test_truncate_to_width_zero_width_returns_empty_string() -> None:
    assert _truncate_to_width("anything", 0) == ""


def test_truncate_to_width_negative_width_returns_empty_string() -> None:
    assert _truncate_to_width("anything", -3) == ""


def test_truncate_to_width_within_limit_returns_unchanged() -> None:
    assert _truncate_to_width("hi", 5) == "hi"


def test_truncate_to_width_wide_glyph_does_not_fit_pads_remainder() -> None:
    # "a漢" measures 3 columns (1 + 2). Truncating to 2 columns must keep
    # "a" (1 col) and pad to width with a space so the final string is
    # exactly 2 cells wide — the wide glyph is dropped because it would
    # overflow the budget.
    out = _truncate_to_width("a漢", 2)
    assert display_width(out) == 2
    assert out == "a "


def test_truncate_to_width_control_char_counted_as_one_column() -> None:
    # ``wcwidth("\x01") == -1`` should be coerced to 1 inside the loop.
    out = _truncate_to_width("a\x01b", 2)
    assert out == "a\x01"


def test_sanitize_layout_text_empty_string_short_circuits() -> None:
    # Hits the early-return branch.
    assert sanitize_layout_text("") == ""


def test_sanitize_layout_text_expands_tabs() -> None:
    # Tabs would otherwise print as eight columns even though they
    # measure as one in display_width.
    assert sanitize_layout_text("a\tb", tab_size=4) == "a   b"


def test_sanitize_layout_text_normalises_carriage_returns() -> None:
    assert sanitize_layout_text("line1\rline2") == "line1\nline2"
    assert sanitize_layout_text("line1\r\nline2") == "line1\nline2"
