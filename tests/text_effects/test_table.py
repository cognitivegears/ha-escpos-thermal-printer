"""Tests for text_effects.table.render_table."""

from __future__ import annotations

import pytest

from custom_components.escpos_printer.text_effects.table import render_table


def test_render_table_basic_ascii() -> None:
    out = render_table(
        [["A", "B"], ["C", "D"]],
        total_width=11,
        style="ascii",
    )
    expected = "+----+----+\n|A   |B   |\n|C   |D   |\n+----+----+"
    assert out == expected


def test_render_table_uses_single_style_for_cp437() -> None:
    out = render_table(
        [["A", "B"]],
        total_width=11,
        style="auto",
        codepage="CP437",
    )
    assert out.startswith("┌")
    assert "│A" in out


def test_render_table_header_adds_separator() -> None:
    out = render_table(
        [["H1", "H2"], ["a", "b"], ["c", "d"]],
        total_width=11,
        style="ascii",
        header=True,
    )
    lines = out.split("\n")
    # top, header, separator, body row, body row, bottom
    assert len(lines) == 6
    assert lines[2] == "+----+----+"  # separator between header and body


def test_render_table_row_separators_between_body_rows() -> None:
    out = render_table(
        [["a", "b"], ["c", "d"], ["e", "f"]],
        total_width=11,
        style="ascii",
        row_separators=True,
    )
    lines = out.split("\n")
    # top, row, sep, row, sep, row, bottom
    assert len(lines) == 7
    assert lines.count("+----+----+") == 4  # top, 2 inner, bottom


def test_render_table_explicit_widths() -> None:
    out = render_table(
        [["a", "bc", "def"]],
        total_width=20,
        column_widths=[3, 5, 7],
        style="ascii",
    )
    lines = out.split("\n")
    assert lines[1] == "|a  |bc   |def    |"


def test_render_table_per_column_alignment() -> None:
    out = render_table(
        [["Item", "Qty", "$"], ["Coffee", "2", "6.00"]],
        total_width=25,
        column_widths=[10, 5, 6],
        column_aligns=["left", "center", "right"],
        style="ascii",
        header=True,
    )
    body = out.split("\n")[3]
    # left-padded "Coffee", center "2", right "6.00"
    assert body == "|Coffee    |  2  |  6.00|"


def test_render_table_style_none_uses_space_join() -> None:
    out = render_table(
        [["a", "b"], ["cd", "ef"]],
        total_width=8,
        column_widths=[3, 3],
        style="none",
    )
    # No border chars, single-space gap between columns.
    assert out == "a   b  \ncd  ef "


def test_render_table_rejects_empty_rows() -> None:
    with pytest.raises(ValueError, match="at least one row"):
        render_table([], total_width=10, style="ascii")


def test_render_table_rejects_widths_too_wide() -> None:
    with pytest.raises(ValueError, match="exceed total_width"):
        render_table(
            [["a", "b"]],
            total_width=5,
            column_widths=[3, 3],
            style="ascii",
        )


def test_render_table_rejects_widths_count_mismatch() -> None:
    with pytest.raises(ValueError, match="column count"):
        render_table(
            [["a", "b", "c"]],
            total_width=20,
            column_widths=[5, 5],
            style="ascii",
        )


def test_render_table_rejects_bad_align() -> None:
    with pytest.raises(ValueError, match="left/center/right"):
        render_table(
            [["a", "b"]],
            total_width=12,
            column_aligns=["left", "middle"],
            style="ascii",
        )


def test_render_table_short_row_padded_with_empty_cells() -> None:
    out = render_table(
        [["a", "b", "c"], ["d"]],
        total_width=16,
        column_widths=[4, 4, 4],
        style="ascii",
    )
    lines = out.split("\n")
    # Second body row's missing cells render as blank padded cells.
    assert lines[2] == "|d   |    |    |"


def test_render_table_wraps_cell_that_exceeds_column_width() -> None:
    out = render_table(
        [["a very long word here", "b"]],
        total_width=14,
        column_widths=[5, 6],
        style="ascii",
    )
    # The first cell wraps into multiple visual lines; each row line is
    # padded to the column width, so all lines are equal width.
    lines = out.split("\n")
    widths = {len(line) for line in lines}
    assert widths == {14}


def test_render_table_distributes_extra_columns_left_first() -> None:
    # total_width=11, n_cols=3 with bordered: usable=11-4=7 → base=2, extra=1
    # → widths [3, 2, 2]
    out = render_table(
        [["a", "b", "c"]],
        total_width=11,
        style="ascii",
    )
    body = out.split("\n")[1]
    assert body == "|a  |b |c |"


def test_render_table_warns_once_on_wide_chars(caplog) -> None:  # type: ignore[no-untyped-def]
    """CJK / fullwidth content triggers a single alignment warning."""
    import logging

    caplog.set_level(logging.WARNING, logger="custom_components.escpos_printer.text_effects.table")
    render_table(
        [["商品", "100"], ["税", "10"]],
        total_width=14,
        style="ascii",
    )
    warnings = [r for r in caplog.records if "wide-width" in r.getMessage()]
    assert len(warnings) == 1


def test_render_table_no_warning_for_ascii(caplog) -> None:  # type: ignore[no-untyped-def]
    import logging

    caplog.set_level(logging.WARNING, logger="custom_components.escpos_printer.text_effects.table")
    render_table(
        [["Item", "Price"], ["Apple", "1.00"]],
        total_width=20,
        style="ascii",
    )
    warnings = [r for r in caplog.records if "wide-width" in r.getMessage()]
    assert warnings == []


def test_render_table_cjk_cell_pads_correctly() -> None:
    """A cell containing CJK (2-cell glyphs) is padded with the correct visual gap."""
    from custom_components.escpos_printer.text_effects.table import render_table as _rt

    # "漢字" = 4 cells; column width 6 → 2 trailing spaces.
    # Borderless to make the assertion clean.
    out = _rt(
        [["漢字", "X"]],
        total_width=10,
        column_widths=[6, 3],
        style="none",
    )
    # One inter-column space (style=none uses single-space joiner).
    assert out == "漢字   X  "


def test_render_table_tab_is_expanded_in_cells() -> None:
    """Tabs inside a cell expand to spaces so the width math matches printed output."""
    from custom_components.escpos_printer.text_effects.table import render_table as _rt

    out = _rt(
        [["A\tB"]],
        total_width=12,
        column_widths=[12],
        style="none",
    )
    # \t at column 1 jumps to next tab stop (column 4): "A   B" + trailing pad.
    assert out.startswith("A   B")
    assert len(out.replace("\n", "")) == 12
