"""Tests for the last-print timestamp sensor (ROADMAP item 5)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_NETWORK,
)
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig
from custom_components.escpos_printer.printer.network_adapter import NetworkPrinterAdapter
from custom_components.escpos_printer.sensor import LastPrintSensor, async_setup_entry


class _FakeEntry:
    """Lightweight stand-in for ConfigEntry — only the attrs the sensor reads."""

    def __init__(
        self,
        entry_id: str = "abc",
        title: str = "TM-T20II",
        data: dict[str, Any] | None = None,
    ) -> None:
        self.entry_id = entry_id
        self.title = title
        self.data = data or {}


class _FakeHass:
    async def async_add_executor_job(self, fn, *args):  # type: ignore[no-untyped-def]
        return fn(*args)


async def test_print_sets_last_print_but_status_probe_does_not():
    """Paper-moving prints stamp _last_print; a status probe alone does not."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]

    assert adapter._last_print is None
    await adapter.print_text(_FakeHass(), text="hello")
    assert adapter._last_print is not None
    assert adapter._last_print.tzinfo is not None
    assert adapter._last_ok is not None

    fresh = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    fresh_printer = MagicMock()
    fresh_printer.query_status.return_value = b"\x12"
    fresh._connect = lambda: fresh_printer  # type: ignore[method-assign]

    await fresh.get_paper_status(_FakeHass())
    assert fresh._last_print is None
    assert fresh._last_ok is not None


async def test_diagnostics_includes_last_print():
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]

    assert adapter.get_diagnostics()["last_print"] is None
    await adapter.print_text(_FakeHass(), text="hello")
    assert adapter.get_diagnostics()["last_print"] is not None


async def test_setup_creates_last_print_sensor():
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    add = MagicMock()
    await async_setup_entry(MagicMock(), entry, add)  # type: ignore[arg-type]
    sensors = list(add.call_args.args[0])
    assert any(isinstance(s, LastPrintSensor) for s in sensors)


async def test_last_print_sensor_unique_id_is_per_entry():
    assert LastPrintSensor(_FakeEntry("a")).unique_id == "a_last_print"  # type: ignore[arg-type]


async def test_last_print_sensor_unknown_until_first_print():
    entry = _FakeEntry()
    entry.runtime_data = MagicMock()
    entry.runtime_data.adapter._last_print = None
    sensor = LastPrintSensor(entry)  # type: ignore[arg-type]
    await sensor.async_update()
    assert sensor.available is True
    assert sensor.native_value is None


async def test_last_print_sensor_reflects_adapter_value():
    entry = _FakeEntry()
    entry.runtime_data = MagicMock()
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    await adapter.print_text(_FakeHass(), text="hello")
    entry.runtime_data.adapter = adapter

    sensor = LastPrintSensor(entry)  # type: ignore[arg-type]
    await sensor.async_update()
    assert sensor.native_value == adapter._last_print


async def test_last_print_sensor_unavailable_without_adapter():
    sensor = LastPrintSensor(_FakeEntry())  # type: ignore[arg-type]
    await sensor.async_update()
    assert sensor.available is False
    assert sensor.native_value is None


async def test_feed_cut_beep_do_not_stamp_last_print():
    """Control ops (feed/cut/beep) update _last_ok but never _last_print."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]

    await adapter.feed(_FakeHass(), lines=3)
    await adapter.cut(_FakeHass(), mode="full")
    await adapter.beep(_FakeHass())

    assert adapter._last_print is None
    assert adapter._last_ok is not None


async def test_print_qr_and_print_barcode_stamp_last_print():
    """print_qr and print_barcode are print ops -- they stamp _last_print."""
    qr_adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    qr_printer = MagicMock()
    qr_adapter._connect = lambda: qr_printer  # type: ignore[method-assign]
    assert qr_adapter._last_print is None
    await qr_adapter.print_qr(_FakeHass(), data="hello")
    assert qr_adapter._last_print is not None

    barcode_adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    barcode_printer = MagicMock()
    barcode_adapter._connect = lambda: barcode_printer  # type: ignore[method-assign]
    assert barcode_adapter._last_print is None
    await barcode_adapter.print_barcode(_FakeHass(), code="123456", bc="CODE128")
    assert barcode_adapter._last_print is not None


async def test_batch_connection_stamps_last_print():
    """batch_connection is a print op -- it stamps _last_print once on exit."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert adapter._last_print is None
    async with adapter.batch_connection(_FakeHass()) as page:
        await page.print_text(text="hello")
        assert adapter._last_print is None  # not stamped per-print inside the batch
    assert adapter._last_print is not None
