"""Tests for text_effects.borders."""

from __future__ import annotations

import pytest

from custom_components.escpos_printer.text_effects.borders import (
    BOX_STYLES,
    codepage_supports_box_drawing,
    glyphs_for,
    resolve_style,
)


def test_box_styles_includes_all_known_styles() -> None:
    assert set(BOX_STYLES) == {
        "auto",
        "single",
        "double",
        "ascii",
        "asterisk",
        "hash",
        "none",
    }


@pytest.mark.parametrize(
    "codepage",
    ["CP437", "CP850", "CP852", "CP858", "CP866"],
)
def test_codepage_supports_box_drawing_native(codepage: str) -> None:
    assert codepage_supports_box_drawing(codepage)


@pytest.mark.parametrize(
    "codepage",
    ["CP1252", "ISO_8859-1", "ISO_8859-15", None, ""],
)
def test_codepage_does_not_support_box_drawing(codepage) -> None:  # type: ignore[no-untyped-def]
    assert not codepage_supports_box_drawing(codepage)


def test_resolve_auto_picks_single_for_cp437() -> None:
    assert resolve_style("auto", "CP437") == "single"


def test_resolve_auto_picks_ascii_for_cp1252() -> None:
    assert resolve_style("auto", "CP1252") == "ascii"


def test_resolve_passes_through_concrete_styles() -> None:
    for style in ("single", "double", "ascii", "asterisk", "hash", "none"):
        assert resolve_style(style, "CP437") == style


def test_resolve_rejects_unknown_style() -> None:
    with pytest.raises(ValueError, match="Unknown border style"):
        resolve_style("squiggle", "CP437")  # type: ignore[arg-type]


def test_glyphs_for_single_returns_cp437_characters() -> None:
    g = glyphs_for("single")
    assert g.tl == "┌"
    assert g.tr == "┐"
    assert g.bl == "└"
    assert g.br == "┘"
    assert g.h == "─"
    assert g.v == "│"
    assert g.cross == "┼"


def test_glyphs_for_double() -> None:
    g = glyphs_for("double")
    assert g.tl == "╔"
    assert g.h == "═"
    assert g.v == "║"


def test_glyphs_for_ascii() -> None:
    g = glyphs_for("ascii")
    assert g.tl == "+"
    assert g.h == "-"
    assert g.v == "|"


def test_glyphs_for_asterisk_all_asterisks() -> None:
    g = glyphs_for("asterisk")
    # All eleven fields collapse to '*'.
    for attr in ("tl", "tr", "bl", "br", "h", "v", "t_down", "t_up", "t_left", "t_right", "cross"):
        assert getattr(g, attr) == "*"


def test_glyphs_for_hash_all_hash() -> None:
    g = glyphs_for("hash")
    assert g.tl == "#" == g.h == g.v == g.cross


def test_glyphs_for_rejects_auto() -> None:
    with pytest.raises(ValueError, match="concrete style"):
        glyphs_for("auto")


def test_glyphs_for_rejects_none() -> None:
    with pytest.raises(ValueError, match="concrete style"):
        glyphs_for("none")
