from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
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


async def test_print_image_url_download_error(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)

    fake = MagicMock()
    # Mock ClientSession.get to raise
    async def _raise(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise aiohttp.ClientError("download failed")

    with patch("escpos.printer.Network", return_value=fake), \
        patch("aiohttp.ClientSession.get", new=AsyncMock(side_effect=_raise)):
        with pytest.raises(Exception):
            await hass.services.async_call(
                DOMAIN,
                "print_image",
                {"image": "https://example.com/img.png"},
                blocking=True,
            )
    assert any("Downloading image from URL" in rec.message for rec in caplog.records)


async def test_encoding_codepage_warning(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    # Cause _set_codepage to raise
    fake._set_codepage.side_effect = RuntimeError("bad codepage")
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello", "encoding": "XYZ"},
            blocking=True,
        )
    assert any("Unsupported encoding/codepage" in rec.message for rec in caplog.records)


async def test_print_barcode_service_calls_escpos(hass):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_barcode",
            {"code": "4006381333931", "bc": "EAN13", "height": 80, "width": 3},
            blocking=True,
        )
    fake.barcode.assert_called()


async def test_beep_service_logs_when_unsupported(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    # Simulate unsupported buzzer by raising AttributeError
    fake.buzzer.side_effect = AttributeError()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(DOMAIN, "beep", {"times": 2, "duration": 3}, blocking=True)
    # Should warn if not supported
    assert any("does not support buzzer" in rec.message for rec in caplog.records)
