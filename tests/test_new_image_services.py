"""Tests for the new image services and helpers.

Covers:
- ``_build_calibration_png`` standalone (no HA required).
- ``extract_image_kwargs`` accepts unprefixed image-only keys on the
  notify entity (collapses the historic ``dither`` / ``image_dither``
  confusion without breaking existing callers).
- Reliability profile presets resolve to the documented chunk_delay_ms /
  fragment_height pairs.
"""

from __future__ import annotations

import io

from PIL import Image

from custom_components.escpos_printer.const import (
    RELIABILITY_PROFILE_BLUETOOTH,
    RELIABILITY_PROFILE_FAST_LAN,
    RELIABILITY_PROFILE_PRESETS,
)
from custom_components.escpos_printer.image_sources import extract_image_kwargs
from custom_components.escpos_printer.services.print_handlers import (
    _build_calibration_png,
)


def test_calibration_png_builds_at_requested_width():
    raw = _build_calibration_png(384)
    img = Image.open(io.BytesIO(raw))
    assert img.width == 384
    # 7 thresholds * 80px strip + 40px ruler = 600.
    assert img.height == 40 + 7 * 80


def test_calibration_png_works_at_narrow_width():
    raw = _build_calibration_png(256)
    img = Image.open(io.BytesIO(raw))
    assert img.width == 256


def test_extract_image_kwargs_accepts_unprefixed_dither_for_notify():
    """Notify with ``dither: threshold`` (no prefix) should map through."""
    out = extract_image_kwargs(
        {"image": "/x.png", "dither": "threshold"},
        {"align": None},
        prefix="image_",
    )
    assert out["dither"] == "threshold"


def test_extract_image_kwargs_prefers_prefixed_key_over_unprefixed():
    """If both forms are passed, the explicitly-prefixed form wins."""
    out = extract_image_kwargs(
        {"image": "/x.png", "dither": "none", "image_dither": "threshold"},
        {"align": None},
        prefix="image_",
    )
    assert out["dither"] == "threshold"


def test_extract_image_kwargs_does_not_pull_text_side_align():
    """`align` belongs to both text and image — must stay prefixed-only."""
    # No image_align passed; the text-side align in the parent dict
    # must not leak into the image fragment.
    out = extract_image_kwargs(
        {"image": "/x.png", "align": "right"},
        {"align": "center"},
        prefix="image_",
    )
    # Falls back to the printer default, not the text-side `align`.
    assert out["align"] == "center"


def test_reliability_profile_fast_lan_zero_delay():
    preset = RELIABILITY_PROFILE_PRESETS[RELIABILITY_PROFILE_FAST_LAN]
    assert preset["chunk_delay_ms"] == 0
    assert preset["fragment_height"] == 512


def test_reliability_profile_bluetooth_uses_throttle():
    preset = RELIABILITY_PROFILE_PRESETS[RELIABILITY_PROFILE_BLUETOOTH]
    assert preset["chunk_delay_ms"] >= 100
    assert preset["fragment_height"] <= 256
