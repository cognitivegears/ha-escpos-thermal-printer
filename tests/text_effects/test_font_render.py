"""Tests for text_effects.font_render."""

from __future__ import annotations

import pytest

from custom_components.escpos_printer.text_effects.font_render import (
    BUILTIN_FONTS,
    render_text_image,
)


def test_builtin_fonts_set() -> None:
    assert set(BUILTIN_FONTS) == {"dejavu_mono", "dejavu_sans", "dejavu_serif"}


def test_render_text_image_dejavu_serif_loads() -> None:
    img = render_text_image(
        "Hello",
        font_name="dejavu_serif",
        font_size=16,
        max_width_px=200,
    )
    assert img.mode == "L"
    assert img.size[0] == 200
    assert img.size[1] > 0


def test_render_text_image_returns_grayscale_pil_image() -> None:
    img = render_text_image(
        "Hello",
        font_name="dejavu_mono",
        font_size=16,
        max_width_px=200,
    )
    assert img.mode == "L"
    assert img.size[0] == 200
    assert img.size[1] > 0


def test_render_text_image_unknown_font_falls_back_to_default() -> None:
    img = render_text_image(
        "Hi",
        font_name="bogus_font",
        font_size=16,
        max_width_px=120,
    )
    # Did not raise; produced a usable image.
    assert img.mode == "L"


def test_render_text_image_rotation_swaps_dimensions() -> None:
    img = render_text_image("X", font_size=24, max_width_px=200, rotation=0)
    img90 = render_text_image("X", font_size=24, max_width_px=200, rotation=90)
    # 90/270 rotation swaps the aspect ratio relative to the unrotated canvas.
    assert (img.size[0], img.size[1]) == (img90.size[1], img90.size[0])


def test_render_text_image_180_keeps_dimensions() -> None:
    img = render_text_image("X", font_size=24, max_width_px=200, rotation=0)
    img180 = render_text_image("X", font_size=24, max_width_px=200, rotation=180)
    assert img.size == img180.size


def test_render_text_image_rejects_bad_rotation() -> None:
    with pytest.raises(ValueError, match="rotation"):
        render_text_image("X", rotation=45)


def test_render_text_image_rejects_bad_font_size() -> None:
    with pytest.raises(ValueError, match="font_size"):
        render_text_image("X", font_size=0)


def test_render_text_image_rejects_bad_align() -> None:
    with pytest.raises(ValueError, match="align"):
        render_text_image("X", align="middle")


def test_render_text_image_wraps_long_text() -> None:
    # A very long string at narrow width should wrap to multiple lines,
    # producing a taller image than a single short line.
    short = render_text_image("Hi", font_size=14, max_width_px=80)
    long = render_text_image(
        "The quick brown fox jumps over the lazy dog repeatedly",
        font_size=14,
        max_width_px=80,
    )
    assert long.size[1] > short.size[1]


def test_render_text_image_user_font_path_loads(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from pathlib import Path

    bundled = (
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "escpos_printer"
        / "fonts"
        / "DejaVuSansMono.ttf"
    )
    # Copy into tmp_path so we exercise the font_path code branch
    # against a non-bundled location.
    dest = tmp_path / "Mono.ttf"
    dest.write_bytes(bundled.read_bytes())
    img = render_text_image(
        "Hi",
        font_path=str(dest),
        font_size=16,
        max_width_px=120,
    )
    assert img.mode == "L"


def test_render_text_image_rejects_oversize_canvas() -> None:
    """Phase 2 S-H1 / P-H1 regression — canvas-height cap fires.

    A 10 000-newline payload at 96 pt with 3.0 line spacing would
    otherwise allocate ~1.4 GB. The cap rejects the call before
    ``Image.new``.
    """
    with pytest.raises(ValueError, match="exceeds maximum"):
        render_text_image(
            "\n" * 10_000,
            font_name="dejavu_mono",
            font_size=96,
            max_width_px=384,
            line_spacing=3.0,
        )


def test_wrap_to_pixels_char_splits_oversize_word_mid_paragraph() -> None:
    """Phase 1 Q-H1 regression — char-split fires for an oversize word
    that is *not* the first word in a paragraph.

    Pre-fix: ``"hi " + "x" * 500`` would flush ``"hi"``, then place
    the giant token verbatim on the next line and silently overflow
    the canvas. Post-fix every output line stays close to the cap (we
    allow a small per-line slop because PIL's bbox accounts for glyph
    bearing while the char-split sums per-char advance widths).
    """
    from pathlib import Path

    from PIL import ImageFont

    from custom_components.escpos_printer.text_effects.font_render import (
        _wrap_to_pixels,
    )

    bundled = (
        Path(__file__).resolve().parents[2]
        / "custom_components"
        / "escpos_printer"
        / "fonts"
        / "DejaVuSansMono.ttf"
    )
    font = ImageFont.truetype(str(bundled), 14)
    text = "hi " + ("x" * 500)
    max_width_px = 80
    lines = _wrap_to_pixels(text, font, max_width_px=max_width_px)

    # Allow a tiny per-line slop (a few px) because bbox includes glyph
    # bearing that per-char getlength doesn't sum. The key guarantee is
    # that we no longer have a single 500-char overflow line.
    slop = 4
    for line in lines:
        bbox = font.getbbox(line)
        width = max(0, bbox[2] - bbox[0])
        assert width <= max_width_px + slop, (
            f"line {line!r} measures {width}px (cap {max_width_px}px + {slop}px slop)"
        )
    # All the 'x's must be preserved across the produced lines.
    assert sum(line.count("x") for line in lines) == 500
    # And at least one line must be longer than 1 char (otherwise we'd
    # be char-splitting *every* char, which would be a pathological
    # over-fit and a separate bug).
    assert max(line.count("x") for line in lines) > 1
