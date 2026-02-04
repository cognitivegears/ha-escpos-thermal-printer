from unittest.mock import MagicMock, patch

from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_PRINTER_NAME, DOMAIN


async def test_print_image_service_local(hass, tmp_path):  # type: ignore[no-untyped-def]
    img_path = tmp_path / "img.png"
    Image.new("RGB", (10, 10)).save(img_path)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TestPrinter",
        data={CONF_PRINTER_NAME: "TestPrinter"},
        unique_id="cups_TestPrinter",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Dummy"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    fake = MagicMock()
    with patch("escpos.printer.Dummy", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": str(img_path)},
            blocking=True,
        )
    assert fake.image.called
