"""Service-level tests for print_kvtable."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import ServiceValidationError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DEFAULT_LINE_WIDTH, DOMAIN


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


async def test_print_kvtable_borderless_right_aligns_values(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_kvtable",
            {
                "items": [["Subtotal", "$10.00"], ["Tax", "$0.80"], ["Total", "$10.80"]],
                "total_width": 20,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    lines = printed.splitlines()
    # Three rows, no borders, each 20 chars wide.
    assert len(lines) == 3
    for line in lines:
        assert len(line) == 20
    # Values end at column 19 (right-aligned).
    assert lines[0].endswith("$10.00")
    assert lines[2].endswith("$10.80")


async def test_print_kvtable_value_align_left(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_kvtable",
            {
                "items": [["Temp", "72F"], ["Humidity", "45%"]],
                "value_align": "left",
                "total_width": 20,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    lines = printed.splitlines()
    # value_align=left → value column padded right with spaces.
    assert "72F" in lines[0]
    # 72F should appear at the left of the value column (not the right).
    assert lines[0].rstrip().endswith("72F") is False or lines[0].endswith(" ")


async def test_print_kvtable_custom_label_width(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_kvtable",
            {
                "items": [["A", "1"], ["B", "2"]],
                "label_width": 10,
                "total_width": 20,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    lines = printed.splitlines()
    # label_width=10 → first 10 chars are label, then 1 gap (borderless),
    # then 9 chars value, total 20.
    assert len(lines[0]) == 20
    # The label "A" left-aligned occupies position 0.
    assert lines[0].startswith("A")


async def test_print_kvtable_bordered_style(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_kvtable",
            {
                "items": [["A", "1"], ["B", "2"]],
                "style": "ascii",
                "total_width": 15,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    lines = printed.splitlines()
    # ASCII borders → top + 2 rows + bottom = 4 lines.
    assert len(lines) == 4
    assert lines[0].startswith("+")
    assert lines[0].endswith("+")
    assert lines[-1].startswith("+")
    assert lines[-1].endswith("+")


async def test_print_kvtable_rejects_three_col_rows(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_kvtable",
                {"items": [["A", "B", "C"]]},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for 3-col row")


async def test_print_kvtable_rejects_empty_items(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network"):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_kvtable",
                {"items": []},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for empty items")


async def test_print_kvtable_total_width_too_small_raises_service_error(hass) -> None:  # type: ignore[no-untyped-def]
    """Bordered style needs total_width >= 5 for a 2-column table (3 for borders + 2 cells).

    Before this fix, ``_kvtable_widths``'s ``max(2, total_width - overhead)``
    floor let widths sail past ``total_width``, and ``render_table`` raised
    a raw ``ValueError`` instead of a caller-facing ``ServiceValidationError``.
    """
    await _setup_entry(hass)
    with patch("escpos.printer.Network"), pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "print_kvtable",
            {
                "items": [["A", "1"]],
                "style": "ascii",
                "total_width": 4,
            },
            blocking=True,
        )


async def test_print_kvtable_total_width_clamped_to_line_width(hass) -> None:  # type: ignore[no-untyped-def]
    """total_width wider than the printer's line_width is clamped, not shredded.

    Without the clamp, the adapter's ``_wrap_text`` re-wraps the rendered
    layout at ``line_width`` afterward, corrupting borders/columns rendered
    wider than that.
    """
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_kvtable",
            {
                "items": [["Subtotal", "$10.00"]],
                "total_width": DEFAULT_LINE_WIDTH + 50,
            },
            blocking=True,
        )
    printed = fake.text.call_args.args[0]
    lines = printed.splitlines()
    for line in lines:
        assert len(line) <= DEFAULT_LINE_WIDTH


def test_validate_kv_items_shape_does_not_strip() -> None:
    """T-L2 / P-H1: the schema-level validator must be shape-only.

    Per-cell control-character sanitisation runs in
    ``security.sanitise_kv_items`` (dispatched to the executor by the
    handler) — NOT in the voluptuous validator that runs on the event
    loop. If someone re-inlines the strip into the schema, this test
    fails by observing that control bytes survived the validator.
    """
    from custom_components.escpos_printer.services.schemas import _validate_kv_items

    out = _validate_kv_items([["a\x00b", "c\x07d"]])
    # Schema must NOT strip — that's the executor sanitiser's job.
    assert out[0][0] == "a\x00b"
    assert out[0][1] == "c\x07d"


def test_sanitise_kv_items_strips_controls() -> None:
    """T-L2: confirm the executor sanitiser does the strip that the
    schema deliberately skips."""
    from custom_components.escpos_printer.security import sanitise_kv_items

    out = sanitise_kv_items([["a\x00b", "c\x07d"]])
    # security.sanitise_kv_items uses the shared _strip_controls helper
    # which strips C0 except CR/LF/HT (matches validate_text_input).
    assert out[0][0] == "ab"
    assert out[0][1] == "cd"
