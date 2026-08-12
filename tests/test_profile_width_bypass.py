"""Tests for the calibration-only profile-width bypass.

python-escpos raises ``ImageWidthError`` for any image wider than the
profile's declared ``media.width.pixels`` — deliberately printing anyway
when the key is missing. The width-bars calibration step *intends* to
send wider-than-profile bars so hardware clipping can be measured, so it
swaps in a proxy profile with the width key removed for the duration of
the send. These tests run against the real python-escpos ``Dummy``
printer (TM-T20II profile, 576 px) so a library upgrade that moves the
width check or reads other profile attributes during ``image()``/``set()``
fails here instead of on paper.
"""

from __future__ import annotations

from escpos.exceptions import ImageWidthError
from escpos.printer import Dummy
from PIL import Image
import pytest

from custom_components.escpos_printer.printer.image_operations import (
    profile_width_bypass,
)

WIDE = Image.new("1", (640, 44), 1)


def test_dummy_profile_still_refuses_wide_images_without_bypass():
    """Baseline: the guard this bypass exists for is still in the library."""
    printer = Dummy(profile="TM-T20II")
    with pytest.raises(ImageWidthError):
        printer.image(WIDE, impl="bitImageRaster")


@pytest.mark.parametrize("impl", ["bitImageRaster", "bitImageColumn", "graphics"])
def test_bypass_sends_wider_than_profile_image(impl):
    """Inside the bypass, every impl accepts a wider-than-profile image.

    ``set()`` runs too — the first image slice calls it, and it reads
    ``profile.get_font()``; the proxy must delegate everything except
    the width key.
    """
    printer = Dummy(profile="TM-T20II")
    original = printer.profile
    with profile_width_bypass(printer):
        printer.set(align="left", normal_textsize=True)
        printer.image(WIDE, impl=impl)
    assert printer.profile is original
    assert len(printer.output) > 0


def test_bypass_restores_profile_on_error():
    printer = Dummy(profile="TM-T20II")
    original = printer.profile
    with pytest.raises(RuntimeError), profile_width_bypass(printer):
        raise RuntimeError("boom")
    assert printer.profile is original
