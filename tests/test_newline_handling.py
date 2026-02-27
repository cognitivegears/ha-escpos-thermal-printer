"""Tests for newline / text-wrapping behaviour in print_text."""

import sys
from unittest.mock import call, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_PRINTER_NAME, DOMAIN
from custom_components.escpos_printer.printer import EscposPrinterAdapter, PrinterConfig


# ---------------------------------------------------------------------------
# Unit tests for _wrap_text (pure, no HA needed)
# ---------------------------------------------------------------------------


def _make_adapter(line_width: int = 48) -> EscposPrinterAdapter:
    cfg = PrinterConfig(
        printer_name="TestPrinter",
        line_width=line_width,
        codepage=None,
        cups_server=None,
    )
    return EscposPrinterAdapter(cfg)


class TestWrapText:
    """Unit tests for EscposPrinterAdapter._wrap_text."""

    def test_no_wrap_when_line_width_zero(self) -> None:
        adapter = _make_adapter(line_width=0)
        text = "Hello world " * 10
        assert adapter._wrap_text(text) == text

    def test_simple_wrap(self) -> None:
        adapter = _make_adapter(line_width=10)
        result = adapter._wrap_text("Hello World")
        # drop_whitespace=False preserves trailing space on the first wrapped line
        assert result == "Hello \nWorld"

    def test_trailing_newline_preserved(self) -> None:
        adapter = _make_adapter(line_width=48)
        text = "Hello\n"
        assert adapter._wrap_text(text).endswith("\n")

    def test_leading_newline_preserved(self) -> None:
        adapter = _make_adapter(line_width=48)
        text = "\nHello"
        assert adapter._wrap_text(text).startswith("\n")

    def test_multiple_trailing_newlines_preserved(self) -> None:
        adapter = _make_adapter(line_width=48)
        text = "Hello\n\n"
        result = adapter._wrap_text(text)
        assert result.endswith("\n\n")

    def test_width_mult_1_uses_full_cols(self) -> None:
        """width_mult=1 wraps at full line_width."""
        adapter = _make_adapter(line_width=10)
        # 10-char text fits in 10 cols at normal size → no wrap
        assert adapter._wrap_text("1234567890", width_mult=1) == "1234567890"

    def test_width_mult_2_halves_effective_cols(self) -> None:
        """width_mult=2 should wrap at line_width//2 effective columns."""
        adapter = _make_adapter(line_width=10)
        # 6-char text fits at normal but overflows at double-width (effective=5)
        result = adapter._wrap_text("123456", width_mult=2)
        assert "\n" in result, f"Expected wrap but got: {result!r}"

    def test_width_mult_3_thirds_effective_cols(self) -> None:
        """width_mult=3 should wrap at line_width//3 effective columns."""
        adapter = _make_adapter(line_width=12)
        # 5-char text fits at normal (12 cols) but overflows at triple-width (effective=4)
        result = adapter._wrap_text("Hello", width_mult=3)
        assert "\n" in result, f"Expected wrap but got: {result!r}"

    def test_wrap_with_leading_trailing_newlines_and_width_mult(self) -> None:
        """_wrap_text with width_mult preserves surrounding newlines."""
        adapter = _make_adapter(line_width=10)
        text = "\n>>> LIZ <<<\n"
        # ">>> LIZ <<<" is 12 chars; effective width at mult=2 is 5, so wraps
        result = adapter._wrap_text(text, width_mult=2)
        assert result.startswith("\n")
        assert result.endswith("\n")

    def test_short_double_width_text_no_wrap(self) -> None:
        """Short double-width text that fits should not be wrapped."""
        adapter = _make_adapter(line_width=48)
        # ">>> LIZ <<<" = 12 chars; at double-width effective=24; 12 < 24 → no wrap
        text = "\n>>> LIZ <<<\n"
        result = adapter._wrap_text(text, width_mult=2)
        lines = [ln for ln in result.split("\n") if ln]
        assert len(lines) == 1, f"Expected no wrap for short text: {result!r}"


# ---------------------------------------------------------------------------
# Integration tests: line-spacing ESC/POS bytes emitted for height > 1
# ---------------------------------------------------------------------------


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
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
    return entry


async def test_double_height_text_sets_line_spacing(hass):  # type: ignore[no-untyped-def]
    """ESC 3 n should be sent before double-height text and ESC 2 after."""
    await _setup_entry(hass)

    dummy_cls = sys.modules["escpos.printer"].Dummy
    raw_calls: list[bytes] = []

    original_raw = dummy_cls._raw

    def spy_raw(self, data: bytes, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_calls.append(data)
        return original_raw(self, data, *args, **kwargs)

    with patch.object(dummy_cls, "_raw", spy_raw):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "BIG", "height": "double"},
            blocking=True,
        )

    # ESC 3 60  (increase line spacing: 0x1b 0x33 60)
    assert any(b == bytes([0x1B, 0x33, 60]) for b in raw_calls), (
        f"Expected ESC 3 60 in raw calls, got: {raw_calls}"
    )
    # ESC 2  (reset line spacing: 0x1b 0x32)
    assert any(b == bytes([0x1B, 0x32]) for b in raw_calls), (
        f"Expected ESC 2 in raw calls, got: {raw_calls}"
    )


async def test_normal_height_text_no_line_spacing_cmds(hass):  # type: ignore[no-untyped-def]
    """No ESC 3 / ESC 2 should be sent for normal-height text."""
    await _setup_entry(hass)

    dummy_cls = sys.modules["escpos.printer"].Dummy
    raw_calls: list[bytes] = []

    original_raw = dummy_cls._raw

    def spy_raw(self, data: bytes, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_calls.append(data)
        return original_raw(self, data, *args, **kwargs)

    with patch.object(dummy_cls, "_raw", spy_raw):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Normal"},
            blocking=True,
        )

    assert not any(b == bytes([0x1B, 0x33, 30]) for b in raw_calls), (
        "ESC 3 n should NOT be sent for normal-height text"
    )
    assert not any(b == bytes([0x1B, 0x32]) for b in raw_calls), (
        "ESC 2 should NOT be sent for normal-height text"
    )


async def test_triple_height_uses_scaled_line_spacing(hass):  # type: ignore[no-untyped-def]
    """ESC 3 90 (30*3=90) should be sent for triple-height text."""
    await _setup_entry(hass)

    dummy_cls = sys.modules["escpos.printer"].Dummy
    raw_calls: list[bytes] = []

    original_raw = dummy_cls._raw

    def spy_raw(self, data: bytes, *args, **kwargs):  # type: ignore[no-untyped-def]
        raw_calls.append(data)
        return original_raw(self, data, *args, **kwargs)

    with patch.object(dummy_cls, "_raw", spy_raw):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "HUGE", "height": "triple"},
            blocking=True,
        )

    assert any(b == bytes([0x1B, 0x33, 90]) for b in raw_calls), (
        f"Expected ESC 3 90 for triple height, got: {raw_calls}"
    )
