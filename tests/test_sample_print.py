"""Tests for the sample test print composer."""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.sample_print import async_print_sample


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


async def test_sample_print_composes_one_receipt(hass):  # type: ignore[no-untyped-def]
    """Logo image, text sections, and QR go out; a cut follows."""
    entry = await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await async_print_sample(hass, entry)

    assert fake.image.called, "logo did not print"
    assert fake.qr.called, "QR did not print"
    assert fake.cut.called, "receipt was not cut"
    # image (logo) must come before qr on the wire
    names = [c[0] for c in fake.method_calls]
    assert names.index("image") < names.index("qr")


async def test_sample_print_cut_mode_none_falls_back_to_full(hass):  # type: ignore[no-untyped-def]
    """An entry whose default cut is 'none' still cuts (full)."""
    from custom_components.escpos_printer.const import CONF_DEFAULT_CUT

    entry = await _setup_entry(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_DEFAULT_CUT: "none"}
    )
    await hass.async_block_till_done()
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await async_print_sample(hass, entry)
    assert fake.cut.called
