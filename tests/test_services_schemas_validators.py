"""Direct unit tests for the schema-level validators in ``services.schemas``.

Each schema validator runs on the event loop before the handler is
invoked, so its negative branches are the first line of defence for
REST/script callers that bypass the UI form. The full schemas are
exercised indirectly via the service handler tests; this module pokes
the individual validators with bad input to cover the ``vol.Invalid``
branches that the happy-path callers never hit.
"""

from __future__ import annotations

import pytest
import voluptuous as vol

from custom_components.escpos_printer.security import (
    MAX_BOX_WIDTH,
    MAX_TABLE_CELL_LENGTH,
    MAX_TABLE_COLS,
    MAX_TABLE_ROWS,
)
from custom_components.escpos_printer.services.schemas import (
    _validate_column_aligns,
    _validate_column_widths,
    _validate_kv_items,
    _validate_rows_shape,
    _validate_separator_char,
)


def test_validate_rows_shape_rejects_non_list_top_level() -> None:
    with pytest.raises(vol.Invalid, match="rows must be a list"):
        _validate_rows_shape("not a list")


def test_validate_rows_shape_rejects_empty_list() -> None:
    with pytest.raises(vol.Invalid, match="at least one row"):
        _validate_rows_shape([])


def test_validate_rows_shape_rejects_too_many_rows() -> None:
    rows = [["x"]] * (MAX_TABLE_ROWS + 1)
    with pytest.raises(vol.Invalid, match=f"exceeds maximum {MAX_TABLE_ROWS}"):
        _validate_rows_shape(rows)


def test_validate_rows_shape_rejects_non_list_row() -> None:
    with pytest.raises(vol.Invalid, match="each row must be a list"):
        _validate_rows_shape([["ok"], "not a row"])


def test_validate_rows_shape_rejects_too_wide_row() -> None:
    too_wide = [["c"] * (MAX_TABLE_COLS + 1)]
    with pytest.raises(vol.Invalid, match=f"exceeds maximum {MAX_TABLE_COLS}"):
        _validate_rows_shape(too_wide)


def test_validate_rows_shape_accepts_valid_rows() -> None:
    rows = [["a", "b"], ["c", "d"]]
    assert _validate_rows_shape(rows) == rows


def test_validate_column_aligns_rejects_non_list() -> None:
    with pytest.raises(vol.Invalid, match="column_aligns must be a list"):
        _validate_column_aligns("left")


def test_validate_column_aligns_rejects_invalid_value() -> None:
    with pytest.raises(vol.Invalid, match="left/center/right"):
        _validate_column_aligns(["left", "middle"])


def test_validate_column_aligns_accepts_valid_values() -> None:
    assert _validate_column_aligns(["left", "center", "right"]) == [
        "left",
        "center",
        "right",
    ]


def test_validate_column_widths_rejects_non_list() -> None:
    with pytest.raises(vol.Invalid, match="must be a list of integers"):
        _validate_column_widths("10")


def test_validate_column_widths_rejects_overlong_list() -> None:
    too_many = [5] * (MAX_TABLE_COLS + 1)
    with pytest.raises(vol.Invalid, match=f"exceeds maximum {MAX_TABLE_COLS}"):
        _validate_column_widths(too_many)


def test_validate_column_widths_rejects_non_integer_entry() -> None:
    with pytest.raises(vol.Invalid, match="must be an integer"):
        _validate_column_widths([5, "x"])


def test_validate_column_widths_rejects_out_of_range_entry() -> None:
    with pytest.raises(vol.Invalid, match=f"out of range 1..{MAX_BOX_WIDTH}"):
        _validate_column_widths([0])
    with pytest.raises(vol.Invalid, match=f"out of range 1..{MAX_BOX_WIDTH}"):
        _validate_column_widths([MAX_BOX_WIDTH + 1])


def test_validate_column_widths_accepts_valid_widths() -> None:
    assert _validate_column_widths([5, 10, 20]) == [5, 10, 20]


def test_validate_separator_char_rejects_non_string() -> None:
    with pytest.raises(vol.Invalid, match="char must be a string"):
        _validate_separator_char(42)


def test_validate_separator_char_rejects_wrong_length() -> None:
    with pytest.raises(vol.Invalid, match="exactly one character"):
        _validate_separator_char("ab")
    with pytest.raises(vol.Invalid, match="exactly one character"):
        _validate_separator_char("")


def test_validate_separator_char_rejects_non_ascii_printable() -> None:
    with pytest.raises(vol.Invalid, match="printable ASCII"):
        _validate_separator_char("\x01")
    with pytest.raises(vol.Invalid, match="printable ASCII"):
        _validate_separator_char("漢")


def test_validate_separator_char_accepts_printable_ascii() -> None:
    assert _validate_separator_char("-") == "-"


def test_validate_kv_items_rejects_non_list() -> None:
    with pytest.raises(vol.Invalid, match="must be a list"):
        _validate_kv_items("nope")


def test_validate_kv_items_rejects_empty_list() -> None:
    with pytest.raises(vol.Invalid, match="at least one entry"):
        _validate_kv_items([])


def test_validate_kv_items_rejects_overlong_list() -> None:
    too_many = [["k", "v"]] * (MAX_TABLE_ROWS + 1)
    with pytest.raises(vol.Invalid, match=f"exceeds maximum {MAX_TABLE_ROWS}"):
        _validate_kv_items(too_many)


def test_validate_kv_items_rejects_wrong_entry_shape() -> None:
    with pytest.raises(vol.Invalid, match="2-element \\[label, value\\] list"):
        _validate_kv_items([["only one"]])


def test_validate_kv_items_rejects_overlong_cell() -> None:
    long_value = "x" * (MAX_TABLE_CELL_LENGTH + 1)
    with pytest.raises(vol.Invalid, match=f"exceeds maximum {MAX_TABLE_CELL_LENGTH}"):
        _validate_kv_items([["label", long_value]])


def test_validate_kv_items_accepts_valid_input() -> None:
    items = [["temp", "72"], ["humidity", None]]
    assert _validate_kv_items(items) == items
