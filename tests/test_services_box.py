"""Service-level tests for print_box."""

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


async def test_print_box_calls_printer_text(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_box",
            {"text": "Hi", "style": "ascii", "total_width": 10},
            blocking=True,
        )
    fake.text.assert_called_once()
    printed = fake.text.call_args.args[0]
    # ASCII border with width 10 → 10-char-wide rows.
    lines = printed.splitlines()
    assert lines[0] == "+--------+"
    assert lines[1] == "|Hi      |"
    assert lines[-1] == "+--------+"


async def test_print_box_auto_picks_single_for_cp437(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_box",
            {"text": "Hi", "total_width": 8},
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    # Auto + CP437 default → single-line glyphs.
    assert printed.split("\n")[0].startswith("┌")


async def test_print_box_padding_adds_blank_rows(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_box",
            {"text": "X", "style": "ascii", "padding": 2, "total_width": 5},
            blocking=True,
        )
    lines = fake.text.call_args.args[0].splitlines()
    # top + 2 padding + 1 content + 2 padding + bottom = 7
    assert len(lines) == 7


async def test_print_box_invalid_style_rejected_at_schema(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_box",
                {"text": "Hi", "style": "fancy"},
                blocking=True,
            )
        except vol.Invalid:
            return
        # HA may wrap voluptuous errors; fail only if the call succeeded.
        raise AssertionError("expected voluptuous error for bad style")


async def test_print_box_strips_control_chars_before_layout(hass) -> None:  # type: ignore[no-untyped-def]
    """Phase 2 S-M1 regression — the handler runs ``validate_text_input``
    before ``render_box`` so an injected ESC byte doesn't (a) reach the
    adapter and (b) doesn't widen the laid-out columns.

    Before the fix, ``handle_print_box`` passed ``call.data[ATTR_TEXT]``
    straight into the renderer. A row containing ``\\x1b`` was counted
    as one column and shifted the right border one place to the left.
    """
    await _setup_entry(hass)
    fake_clean = MagicMock()
    fake_dirty = MagicMock()
    with patch("escpos.printer.Network", return_value=fake_clean):
        await hass.services.async_call(
            DOMAIN,
            "print_box",
            {"text": "Hi", "style": "ascii", "total_width": 8},
            blocking=True,
        )
    with patch("escpos.printer.Network", return_value=fake_dirty):
        await hass.services.async_call(
            DOMAIN,
            "print_box",
            {"text": "H\x1bi", "style": "ascii", "total_width": 8},
            blocking=True,
        )
    clean = fake_clean.text.call_args.args[0]
    dirty = fake_dirty.text.call_args.args[0]
    # ESC stripped → both outputs render identically, no column drift.
    assert clean == dirty
    assert "\x1b" not in dirty
