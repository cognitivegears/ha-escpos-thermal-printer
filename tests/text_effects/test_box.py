"""Tests for text_effects.box.render_box."""

from __future__ import annotations

import pytest

from custom_components.escpos_printer.text_effects.box import render_box


def test_render_box_single_style_basic() -> None:
    out = render_box("Hi", inner_width=4, style="single", codepage="CP437")
    assert out == "┌────┐\n│Hi  │\n└────┘"


def test_render_box_ascii_style_basic() -> None:
    out = render_box("Hi", inner_width=4, style="ascii")
    assert out == "+----+\n|Hi  |\n+----+"


def test_render_box_double_style() -> None:
    out = render_box("X", inner_width=3, style="double", codepage="CP437")
    assert out == "╔═══╗\n║X  ║\n╚═══╝"


def test_render_box_with_padding_adds_blank_rows() -> None:
    out = render_box("A", inner_width=3, style="single", codepage="CP437", padding=1)
    lines = out.split("\n")
    # top, padding, content, padding, bottom = 5 lines
    assert len(lines) == 5
    assert lines[1] == "│   │"
    assert lines[2] == "│A  │"
    assert lines[3] == "│   │"


def test_render_box_align_center() -> None:
    out = render_box("Hi", inner_width=6, style="ascii", align="center")
    # Content row should be "|  Hi  |" (2 leading, 2 trailing spaces)
    content_row = out.split("\n")[1]
    assert content_row == "|  Hi  |"


def test_render_box_align_right() -> None:
    out = render_box("Hi", inner_width=6, style="ascii", align="right")
    content_row = out.split("\n")[1]
    assert content_row == "|    Hi|"


def test_render_box_wraps_long_text() -> None:
    text = "The quick brown fox jumps"
    out = render_box(text, inner_width=10, style="ascii")
    lines = out.split("\n")
    # 1 top border + N content lines + 1 bottom border
    assert lines[0] == "+----------+"
    assert lines[-1] == "+----------+"
    # Each interior line is exactly inner_width+2 columns wide.
    for line in lines:
        assert len(line) == 12


def test_render_box_auto_resolves_per_codepage() -> None:
    # CP437 → single; CP1252 → ascii
    single = render_box("X", inner_width=3, style="auto", codepage="CP437")
    ascii_ = render_box("X", inner_width=3, style="auto", codepage="CP1252")
    assert "┌" in single
    assert "+" in ascii_
    assert "┌" not in ascii_


def test_render_box_style_none_omits_borders() -> None:
    out = render_box("Hi\nWorld", inner_width=8, style="none", align="left")
    # No border characters; lines padded to inner_width.
    lines = out.split("\n")
    assert lines == ["Hi      ", "World   "]


def test_render_box_rejects_negative_padding() -> None:
    with pytest.raises(ValueError, match="padding"):
        render_box("X", inner_width=5, style="ascii", padding=-1)


def test_render_box_rejects_inner_width_zero() -> None:
    with pytest.raises(ValueError, match="inner_width"):
        render_box("X", inner_width=0, style="ascii")


def test_render_box_rejects_bad_align() -> None:
    with pytest.raises(ValueError, match="align"):
        render_box("X", inner_width=5, style="ascii", align="middle")


def test_render_box_preserves_empty_lines() -> None:
    out = render_box("A\n\nB", inner_width=3, style="ascii")
    lines = out.split("\n")
    # top + 3 content (A, blank, B) + bottom
    assert len(lines) == 5
    assert lines[1] == "|A  |"
    assert lines[2] == "|   |"
    assert lines[3] == "|B  |"


def test_render_box_cjk_consumes_two_columns_per_glyph() -> None:
    """CJK ideographs are 2-cell glyphs; padding must reserve the right gap."""
    # 漢 = 2 columns; inner_width=6 → 6-2 = 4 trailing spaces.
    out = render_box("漢", inner_width=6, style="ascii")
    content_row = out.split("\n")[1]
    assert content_row == "|漢    |"


def test_render_box_emoji_consumes_two_columns() -> None:
    """Most emoji are 2-cell (East Asian Wide)."""
    out = render_box("✅", inner_width=5, style="ascii")
    content_row = out.split("\n")[1]
    # ✅ is wide (2 cells); 5 - 2 = 3 trailing spaces.
    assert content_row == "|✅   |"


def test_render_box_zero_width_combining_marks_do_not_consume_columns() -> None:
    """A combining acute accent adds 0 cells — total still equals the base char."""
    # "e" + combining acute = 1 base + 0 combining = 1 cell.
    text = "é"  # é
    out = render_box(text, inner_width=4, style="ascii")
    content_row = out.split("\n")[1]
    # Display width = 1, padded to 4 with 3 trailing spaces.
    assert content_row == f"|{text}   |"


def test_render_box_tab_is_expanded() -> None:
    """Tabs are expanded to spaces so width accounting matches the printed output."""
    out = render_box("A\tB", inner_width=8, style="ascii")
    content_row = out.split("\n")[1]
    # \t with default tabsize=4: "A" + 3 spaces (to next tab stop) + "B" = 5 cells.
    assert content_row == "|A   B   |"
