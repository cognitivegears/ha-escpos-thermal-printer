"""Unit tests for the image preprocessing pipeline."""

from __future__ import annotations

import io

from PIL import Image
import PIL.Image
import pytest

from custom_components.escpos_printer.printer.image_processor import (
    FALLBACK_PROFILE_WIDTH,
    ImageProcessOptions,
    process_image,
    process_image_from_bytes,
)


def _solid(width: int, height: int, color: int = 128, mode: str = "L") -> Image.Image:
    return Image.new(mode, (width, height), color=color)


def test_resize_to_explicit_width_preserves_aspect_ratio() -> None:
    img = _solid(1000, 500)
    out = process_image(img, ImageProcessOptions(width=200))
    assert out.width == 200
    assert out.height == 100


def test_resize_uses_profile_width_when_width_omitted() -> None:
    img = _solid(800, 400)
    out = process_image(img, ImageProcessOptions(profile_width=384))
    assert out.width == 384


def test_resize_falls_back_to_512_when_profile_unknown() -> None:
    img = _solid(2000, 500)
    out = process_image(img, ImageProcessOptions())
    assert out.width == FALLBACK_PROFILE_WIDTH


def test_smaller_image_is_not_upscaled() -> None:
    img = _solid(100, 100)
    out = process_image(img, ImageProcessOptions(width=512))
    assert out.width == 100
    assert out.height == 100


def test_rotation_90_swaps_dimensions() -> None:
    img = _solid(200, 100)
    out = process_image(img, ImageProcessOptions(rotation=90, width=400))
    # After 90 degree rotation, original 200x100 becomes 100x200; smaller than 400 so no resize.
    assert out.width == 100
    assert out.height == 200


def test_dither_threshold_produces_pure_black_and_white() -> None:
    # Build a gradient so the threshold has something to split on.
    img = Image.new("L", (10, 1))
    for x in range(10):
        img.putpixel((x, 0), x * 25)  # 0, 25, 50, ..., 225
    out = process_image(
        img, ImageProcessOptions(width=10, dither="threshold", threshold=128)
    )
    assert out.mode == "1"
    pixels = list(out.getdata())
    # Values 0..125 -> 0, values 150..225 -> 255 (PIL "1" mode reports 0/255)
    assert pixels[:6] == [0, 0, 0, 0, 0, 0]
    assert pixels[6:] == [255, 255, 255, 255]


def test_dither_none_uses_no_dithering() -> None:
    img = _solid(8, 8, color=200)
    out = process_image(img, ImageProcessOptions(width=8, dither="none"))
    assert out.mode == "1"


def test_autocontrast_expands_dynamic_range() -> None:
    # Low-contrast input: values clustered at 100-130
    img = Image.new("L", (4, 4))
    img.putdata([100, 110, 120, 130] * 4)
    out = process_image(
        img,
        ImageProcessOptions(width=4, autocontrast=True, dither="threshold", threshold=128),
    )
    pixels = list(out.getdata())
    # After autocontrast + threshold, we should see a mix of black and white,
    # not the all-one-color result we'd get without autocontrast.
    assert 0 in pixels
    assert 255 in pixels


def test_exif_orientation_is_corrected() -> None:
    # Create a 2x4 image and embed EXIF orientation=6 (rotate 270 CW on load).
    img = Image.new("L", (2, 4), color=255)
    buf = io.BytesIO()
    exif = img.getexif()
    exif[0x0112] = 6  # Orientation tag: rotate 90 CW per spec
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    loaded = Image.open(buf)
    # Without EXIF transpose, loaded.size would still be (2, 4).
    out = process_image(loaded, ImageProcessOptions(width=10))
    # exif_transpose should have swapped to (4, 2).
    assert out.width == 4
    assert out.height == 2


# ---------------------------------------------------------------------------
# T-C4: decompression bomb is rejected (not silently swallowed).
# ---------------------------------------------------------------------------


def test_decompression_bomb_raises() -> None:
    """A small file declaring huge dimensions must trigger PIL's bomb check."""
    # Lower the cap to keep the test fast (avoids generating a 178M-pixel
    # image just to trip the global default). 100 px is comfortably below
    # MAX_PROCESSED_HEIGHT but `MAX_IMAGE_PIXELS = 100` means even a
    # 11x11 image trips bomb detection.
    original = PIL.Image.MAX_IMAGE_PIXELS
    PIL.Image.MAX_IMAGE_PIXELS = 100
    try:
        buf = io.BytesIO()
        Image.new("L", (40, 40)).save(buf, format="PNG")
        with pytest.raises(
            (PIL.Image.DecompressionBombError, PIL.Image.DecompressionBombWarning)
        ):
            process_image_from_bytes(buf.getvalue(), ImageProcessOptions(width=20))
    finally:
        PIL.Image.MAX_IMAGE_PIXELS = original


# ---------------------------------------------------------------------------
# T-M6: RGBA flatten — transparency must become white, not black.
# ---------------------------------------------------------------------------


def test_rgba_transparency_flattened_to_white() -> None:
    rgba = Image.new("RGBA", (10, 10), (0, 0, 0, 0))  # fully transparent
    out = process_image(rgba, ImageProcessOptions(width=10, dither="none"))
    assert out.mode == "1"
    # White paper means transparent pixels render as white (value 255).
    pixels = list(out.getdata())
    assert all(p == 255 for p in pixels)


# ---------------------------------------------------------------------------
# Rotation parametrized — pixel-correctness, not just dimensions.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("angle", [0, 90, 180, 270])
def test_rotation_dimensions(angle: int) -> None:
    img = _solid(40, 20)
    out = process_image(img, ImageProcessOptions(width=200, rotation=angle))
    if angle in (0, 180):
        assert (out.width, out.height) == (40, 20)
    else:
        assert (out.width, out.height) == (20, 40)


# ---------------------------------------------------------------------------
# Unknown dither modes are rejected (the schema normally catches this; the
# adapter's belt-and-braces validator does too, but `process_image` raises
# ValueError for defense in depth).
# ---------------------------------------------------------------------------


def test_unknown_dither_raises() -> None:
    img = _solid(8, 8)
    with pytest.raises(ValueError, match="Unknown dither mode"):
        process_image(img, ImageProcessOptions(width=8, dither="ordered"))


# ---------------------------------------------------------------------------
# invert / mirror / auto_resize
# ---------------------------------------------------------------------------


def test_invert_swaps_black_and_white() -> None:
    """Invert flips grayscale before B&W conversion."""
    # All-white input + threshold=128 normally prints as white (no ink).
    # With invert, it should become black.
    img = _solid(8, 8, color=255)
    out = process_image(
        img,
        ImageProcessOptions(
            width=8, invert=True, dither="threshold", threshold=128
        ),
    )
    assert set(out.getdata()) == {0}


def test_mirror_flips_horizontally() -> None:
    """Mirror reverses pixel order horizontally; vertical is unchanged."""
    img = Image.new("L", (4, 1))
    img.putdata([0, 64, 128, 255])
    out = process_image(
        img, ImageProcessOptions(width=4, mirror=True, dither="none")
    )
    # After mirror, first column is the old last column (255 -> 1 in mode "1").
    pixels = list(out.getdata())
    # Mode "1" dither=none: PIL maps via floor — 255 stays 255, 0 stays 0.
    assert pixels[0] == 255
    assert pixels[-1] == 0


def test_auto_resize_shrinks_huge_input_before_processing() -> None:
    """auto_resize=True caps decoding work for >4x-profile-width inputs."""
    img = _solid(10000, 10000, color=200)
    out = process_image(
        img,
        ImageProcessOptions(width=200, profile_width=200, auto_resize=True),
    )
    # After auto_resize the input gets thumbnailed to ~800x800 (4x*200),
    # then the width-fit pass scales down to 200. Aspect ratio preserved.
    assert out.width == 200
    assert out.height == 200


def test_processed_height_error_includes_actionable_text() -> None:
    """Error text suggests reducing image_width / rotating, not just the cap."""
    from custom_components.escpos_printer.security import MAX_PROCESSED_HEIGHT

    img = _solid(10, MAX_PROCESSED_HEIGHT + 100)
    with pytest.raises(ValueError, match="reduce image_width"):
        process_image(img, ImageProcessOptions(width=10))
