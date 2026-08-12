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

import base64
import io
from unittest.mock import patch

from escpos.exceptions import ImageWidthError
from escpos.printer import Dummy
from homeassistant.const import CONF_HOST, CONF_PORT
from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
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

    ``set()`` runs too — the first image slice calls it, and it may read
    other profile attributes; the proxy must delegate everything except
    the width key.
    """
    printer = Dummy(profile="TM-T20II")
    original = printer.profile
    with profile_width_bypass(printer):
        printer.set(align="left", normal_textsize=True)
        printer.image(WIDE, impl=impl)
    assert printer.profile is original
    assert len(printer.output) > 0


def test_bypass_profile_delegates_other_attributes():
    """Only ``media.width`` is hidden; everything else reaches the real profile."""
    printer = Dummy(profile="TM-T20II")
    with profile_width_bypass(printer):
        assert "width" not in printer.profile.profile_data["media"]
        # Attribute lookups (``set()`` uses ``get_font``) must delegate.
        assert printer.profile.get_font("a") == 0
        assert printer.profile.name == "TM-T20II"


def test_bypass_restores_profile_on_error():
    # try/except instead of pytest.raises: CodeQL doesn't model
    # pytest.raises' exception suppression and flags the trailing
    # assert as unreachable.
    printer = Dummy(profile="TM-T20II")
    original = printer.profile
    try:
        with profile_width_bypass(printer):
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    assert printer.profile is original


# ---------------------------------------------------------------------------
# Batch-page integration: the ignore_profile_width flag end to end.
# ---------------------------------------------------------------------------


def _bar_data_uri(width: int) -> str:
    img = Image.new("1", (width, 20), 1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


async def _setup_entry(hass) -> MockConfigEntry:  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_batch_page_print_image_bypasses_profile_width(hass):  # type: ignore[no-untyped-def]
    """ignore_profile_width=True sends a wider-than-profile image and restores the profile."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    fake_printer = Dummy(profile="TM-T20II")
    original = fake_printer.profile
    with patch.object(adapter, "_connect", return_value=fake_printer):
        async with adapter.batch_connection(hass) as page:
            await page.print_image(
                image=_bar_data_uri(640),
                width=640,
                feed=1,
                ignore_profile_width=True,
            )

    assert fake_printer.profile is original
    assert len(fake_printer.output) > 0


async def test_batch_page_print_image_guarded_by_default(hass):  # type: ignore[no-untyped-def]
    """Without the flag, python-escpos's profile-width refusal still applies."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    fake_printer = Dummy(profile="TM-T20II")
    with (
        patch.object(adapter, "_connect", return_value=fake_printer),
        pytest.raises(ImageWidthError),
    ):
        async with adapter.batch_connection(hass) as page:
            await page.print_image(image=_bar_data_uri(640), width=640, feed=1)
