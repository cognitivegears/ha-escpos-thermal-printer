"""Service-level tests for print_table."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
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


async def test_print_table_renders_three_columns(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_table",
            {
                "rows": [["Item", "Qty", "Price"], ["Coffee", "2", "$6.00"]],
                "style": "ascii",
                "header": True,
                "total_width": 26,
            },
            blocking=True,
        )
    fake.text.assert_called_once()
    printed = fake.text.call_args.args[0]
    lines = printed.splitlines()
    # top border + header + sep + body + bottom = 5
    assert len(lines) == 5
    assert lines[0].startswith("+")
    assert "Item" in lines[1]
    assert "Coffee" in lines[3]


async def test_print_table_row_separators(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_table",
            {
                "rows": [["a", "b"], ["c", "d"], ["e", "f"]],
                "style": "ascii",
                "row_separators": True,
                "total_width": 11,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    # 4 horizontal separators (top + 2 between rows + bottom).
    assert printed.count("+----+----+") == 4


async def test_print_table_rejects_bad_rows_shape_at_schema(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_table",
                {"rows": "not a list"},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for bad rows shape")


async def test_print_table_uses_printer_line_width_when_total_width_omitted(
    hass,  # type: ignore[no-untyped-def]
) -> None:
    """Default total_width comes from adapter config.line_width (48)."""
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_table",
            {
                "rows": [["a", "b"], ["c", "d"]],
                "style": "ascii",
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    # Every line is exactly the default printer width (48).
    assert all(len(line) == 48 for line in printed.splitlines())


async def test_print_table_with_style_none(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_table",
            {
                "rows": [["a", "b"], ["c", "d"]],
                "style": "none",
                "column_widths": [4, 4],
                "total_width": 10,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    # No border characters anywhere.
    for ch in "+-|┌─│":
        assert ch not in printed
