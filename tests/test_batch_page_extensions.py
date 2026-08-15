"""Tests for _BatchPage styled-text passthrough and QR printing."""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass, host="1.2.3.4"):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: host, CONF_PORT: 9100},
        title=f"ESC/POS {host}",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network", return_value=MagicMock()):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_batch_page_styled_text_and_qr(hass):  # type: ignore[no-untyped-def]
    """Styled kwargs reach printer.set(); qr() is issued on the held connection."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        async with adapter.batch_connection(hass) as page:
            await page.print_text(text="Loud\n", bold=True, align="center")
            await page.print_qr(data="https://example.com")

    assert fake.qr.called
    qr_args, _qr_kwargs = fake.qr.call_args
    assert qr_args[0] == "https://example.com"
    # bold=True must have been forwarded to printer.set() by the text half
    set_kwargs = [kw for _, kw in fake.set.call_args_list]
    assert any(kw.get("bold") for kw in set_kwargs)
