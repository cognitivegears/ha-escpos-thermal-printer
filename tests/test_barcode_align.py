"""Tests for print_barcode align/align_ct override precedence.

python-escpos re-centers a barcode (align_ct) after printer.set(align=...),
so an explicit ``align`` must force ``align_ct=False`` unless the caller
also sets ``align_ct`` explicitly.
"""

from unittest.mock import AsyncMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


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


async def test_explicit_align_overrides_default_align_ct(hass):  # type: ignore[no-untyped-def]
    """align="left" alone must win over the align_ct default."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_barcode", AsyncMock()) as mock_print:
        await hass.services.async_call(
            DOMAIN,
            "print_barcode",
            {"code": "123456", "bc": "CODE128", "align": "left"},
            blocking=True,
        )
    assert mock_print.call_args.kwargs["align_ct"] is False
    assert mock_print.call_args.kwargs["align"] == "left"


async def test_no_align_fields_defaults_to_centered(hass):  # type: ignore[no-untyped-def]
    """Neither field set must stay byte-identical to today: align_ct=True."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_barcode", AsyncMock()) as mock_print:
        await hass.services.async_call(
            DOMAIN,
            "print_barcode",
            {"code": "123456", "bc": "CODE128"},
            blocking=True,
        )
    assert mock_print.call_args.kwargs["align_ct"] is True


async def test_explicit_align_ct_honored_over_align(hass):  # type: ignore[no-untyped-def]
    """An explicit align_ct=True is honored even alongside an explicit align."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_barcode", AsyncMock()) as mock_print:
        await hass.services.async_call(
            DOMAIN,
            "print_barcode",
            {"code": "123456", "bc": "CODE128", "align": "left", "align_ct": True},
            blocking=True,
        )
    assert mock_print.call_args.kwargs["align_ct"] is True
