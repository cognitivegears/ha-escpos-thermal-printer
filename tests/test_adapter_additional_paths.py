from unittest.mock import MagicMock, patch

from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={"host": "1.2.3.4", "port": 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_print_image_resizes_large_local_image(hass, tmp_path, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)

    # Create a big image to trigger resize (>512px width)
    img_path = tmp_path / "big.png"
    img = Image.new("L", (1024, 200))
    img.save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": str(img_path), "high_density": True},
            blocking=True,
        )
    # Ensure image() was called and resize log present
    assert fake.image.called
    assert any("Resized image" in rec.message for rec in caplog.records)


async def test_beep_success_branch(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    # Provide buzzer attribute to go through success path
    fake.buzzer = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(DOMAIN, "beep", {"times": 2, "duration": 3}, blocking=True)
    fake.buzzer.assert_called()
    assert any("beep begin" in rec.message for rec in caplog.records)
