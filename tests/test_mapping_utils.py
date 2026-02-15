"""Tests for printer mapping_utils functions."""

import pytest

from custom_components.escpos_printer.printer.mapping_utils import map_multiplier


class TestMapMultiplier:
    """Tests for map_multiplier."""

    def test_named_normal(self) -> None:
        assert map_multiplier("normal") == 1

    def test_named_double(self) -> None:
        assert map_multiplier("double") == 2

    def test_named_triple(self) -> None:
        assert map_multiplier("triple") == 3

    def test_named_case_insensitive(self) -> None:
        assert map_multiplier("DOUBLE") == 2
        assert map_multiplier("Triple") == 3

    def test_none_returns_1(self) -> None:
        assert map_multiplier(None) == 1

    def test_int_passthrough(self) -> None:
        assert map_multiplier(1) == 1
        assert map_multiplier(2) == 2
        assert map_multiplier(4) == 4
        assert map_multiplier(8) == 8

    def test_int_clamped_to_range(self) -> None:
        assert map_multiplier(0) == 1
        assert map_multiplier(-1) == 1
        assert map_multiplier(9) == 8
        assert map_multiplier(100) == 8

    def test_numeric_string(self) -> None:
        assert map_multiplier("2") == 2
        assert map_multiplier("4") == 4
        assert map_multiplier("8") == 8

    def test_numeric_string_clamped(self) -> None:
        assert map_multiplier("0") == 1
        assert map_multiplier("10") == 8

    def test_unrecognized_string_returns_1(self) -> None:
        assert map_multiplier("big") == 1
        assert map_multiplier("") == 1
