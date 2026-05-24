"""Cover the fallback paths in printer/control_operations.py.

The ``feed`` / ``cut`` / ``beep`` mixins all have defensive branches
for printers that lack a given method or whose primary method raises.
These tests pin down those branches so they don't silently rot.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig
from custom_components.escpos_printer.printer.factory import create_printer_adapter


def _make_adapter() -> Any:
    return create_printer_adapter(NetworkPrinterConfig(host="1.2.3.4", port=9100))


async def _setup_entry(hass: Any) -> MockConfigEntry:
    """Set up an entry so the integration is wired up. We then drive a
    freshly-built adapter directly so we can swap the underlying printer
    surface to exercise the fallback branches."""
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


class _PrinterBase:
    """Minimal printer surface satisfying adapter setup/teardown."""

    def close(self) -> None:
        pass

    def _set_codepage(self, *_: Any, **__: Any) -> None:
        pass


async def test_feed_invalid_lines_coerces_to_one(hass: Any) -> None:
    """A non-int ``lines`` argument coerces to 1 (defensive path)."""
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        # The service-layer schema coerces to int, so call the adapter
        # directly to exercise the int-coercion fallback inside ``feed``.
        await adapter.feed(hass, lines="not-an-int")  # type: ignore[arg-type]
    fake.control.assert_called_once_with("LF")


async def test_feed_control_exception_falls_back_to_ln(hass: Any) -> None:
    """If ``printer.control`` raises, ``feed`` falls through to ``printer.ln``."""
    await _setup_entry(hass)
    fake = MagicMock()
    fake.control = MagicMock(side_effect=RuntimeError("no control"))
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.feed(hass, lines=3)
    fake.ln.assert_called_once_with(3)


async def test_feed_falls_back_to_raw_when_ln_missing(hass: Any) -> None:
    """No ``control`` and no ``ln`` → falls through to ``_raw``."""

    class _PrinterRawOnly(_PrinterBase):
        def __init__(self) -> None:
            self.raw_calls: list[bytes] = []

        def _raw(self, data: bytes) -> None:
            self.raw_calls.append(data)

    await _setup_entry(hass)
    fake = _PrinterRawOnly()
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.feed(hass, lines=4)
    assert fake.raw_calls == [b"\n\n\n\n"]


async def test_feed_falls_back_to_text_when_raw_raises(hass: Any) -> None:
    """No ``control``, no ``ln``, ``_raw`` raises → falls through to ``text``."""

    class _PrinterTextOnly(_PrinterBase):
        def __init__(self) -> None:
            self.text_calls: list[str] = []

        def _raw(self, _data: bytes) -> None:
            raise OSError("no raw")

        def text(self, s: str) -> None:
            self.text_calls.append(s)

    await _setup_entry(hass)
    fake = _PrinterTextOnly()
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.feed(hass, lines=2)
    assert fake.text_calls == ["\n", "\n"]


async def test_cut_invalid_mode_defaults_to_full(hass: Any, caplog: Any) -> None:
    """Unknown cut mode logs a warning and defaults to FULL."""
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.cut(hass, mode="this-is-not-a-cut-mode")
    fake.cut.assert_called_once_with(mode="FULL")
    assert any("Invalid cut mode" in rec.message for rec in caplog.records)


async def test_beep_uses_beep_method_when_no_buzzer(hass: Any) -> None:
    """If the printer exposes ``beep`` but not ``buzzer``, that path is taken."""

    class _PrinterBeepOnly(_PrinterBase):
        def __init__(self) -> None:
            self.beep_calls: list[tuple[int, int]] = []

        def beep(self, times: int, duration: int) -> None:
            self.beep_calls.append((times, duration))

    await _setup_entry(hass)
    fake = _PrinterBeepOnly()
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.beep(hass, times=3, duration=4)
    assert fake.beep_calls == [(3, 4)]


async def test_beep_warns_when_no_buzzer_or_beep(hass: Any, caplog: Any) -> None:
    """Printer with neither ``buzzer`` nor ``beep`` logs a warning, no crash."""
    await _setup_entry(hass)
    fake = _PrinterBase()
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.beep(hass, times=2, duration=2)
    assert any("does not support buzzer" in rec.message for rec in caplog.records)


async def test_beep_swallows_attribute_error_from_buzzer(hass: Any, caplog: Any) -> None:
    """A buzzer that raises AttributeError is treated as unsupported (warn, no crash)."""
    await _setup_entry(hass)
    fake = MagicMock()
    fake.buzzer = MagicMock(side_effect=AttributeError("nope"))
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.beep(hass, times=1, duration=1)
    assert any("does not support buzzer" in rec.message for rec in caplog.records)


async def test_beep_swallows_generic_exception_from_buzzer(hass: Any, caplog: Any) -> None:
    """A buzzer that raises an unexpected error logs at debug and does not crash."""
    import logging

    caplog.set_level(logging.DEBUG)
    await _setup_entry(hass)
    fake = MagicMock()
    fake.buzzer = MagicMock(side_effect=RuntimeError("buzzer fried"))
    with patch("escpos.printer.Network", return_value=fake):
        adapter = _make_adapter()
        await adapter.beep(hass, times=1, duration=1)
    assert any("Beep failed" in rec.message for rec in caplog.records)
