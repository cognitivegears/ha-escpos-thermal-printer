"""Service-level tests for print_separator."""

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


async def test_print_separator_default_fills_line_width(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_separator",
            {},
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    # Default char "-", default width = printer line width (48 in
    # DEFAULT_LINE_WIDTH), single line.
    assert printed == "-" * 48


async def test_print_separator_custom_char_and_width(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_separator",
            {"char": "=", "width": 20},
            blocking=True,
        )
    assert fake.text.call_args.args[0] == "=" * 20


async def test_print_separator_repeat_emits_n_lines(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_separator",
            {"char": "=", "width": 10, "repeat": 3},
            blocking=True,
        )
    assert fake.text.call_args.args[0] == "==========\n==========\n=========="


async def test_print_separator_rejects_empty_char(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_separator",
                {"char": ""},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for empty char")


async def test_print_separator_rejects_multi_char(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_separator",
                {"char": "--"},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for multi-char")


async def test_print_separator_rejects_control_char(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_separator",
                {"char": "\x1b"},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for control char")
