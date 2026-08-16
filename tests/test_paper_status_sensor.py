"""Tests for the paper status sensor (issue #109)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
)
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig
from custom_components.escpos_printer.printer.network_adapter import NetworkPrinterAdapter
from custom_components.escpos_printer.sensor import (
    SCAN_INTERVAL,
    PaperStatusSensor,
    async_setup_entry,
)


def test_scan_interval_is_five_minutes():
    """Both should_poll sensors were documented as 5-minute polls but had no SCAN_INTERVAL.

    HA's entity-component default is 30s, so battery (D-Bus round-trip)
    and paper-status (fresh printer connection) polls were 10x more
    frequent than intended.
    """
    assert timedelta(minutes=5) == SCAN_INTERVAL


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


@pytest.mark.parametrize(
    ("connection_type", "expected"),
    [
        (CONNECTION_TYPE_NETWORK, True),
        (CONNECTION_TYPE_USB, True),
        (CONNECTION_TYPE_BLUETOOTH, False),
        (CONNECTION_TYPE_SERIAL, False),
    ],
)
async def test_setup_creates_paper_sensor_only_for_readable_transports(connection_type, expected):
    """BT/serial transports are write-only; an empty read would be a false OK."""
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: connection_type})
    add = MagicMock()
    await async_setup_entry(MagicMock(), entry, add)  # type: ignore[arg-type]
    sensors = list(add.call_args.args[0])
    assert any(isinstance(s, PaperStatusSensor) for s in sensors) is expected


@pytest.mark.parametrize(
    ("status", "value", "available"),
    [(2, "ok", True), (1, "low", True), (0, "out", True), (None, None, False), (7, None, False)],
)
async def test_paper_sensor_maps_status_codes(status, value, available):
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    entry.runtime_data = MagicMock()
    entry.runtime_data.adapter.get_paper_status = AsyncMock(return_value=status)
    sensor = PaperStatusSensor(entry)  # type: ignore[arg-type]
    sensor.hass = MagicMock()
    await sensor.async_update()
    assert sensor.available is available
    assert sensor.native_value == value


async def test_paper_sensor_unavailable_without_adapter():
    sensor = PaperStatusSensor(_FakeEntry())  # type: ignore[arg-type]
    sensor.hass = MagicMock()
    await sensor.async_update()
    assert sensor.available is False


async def test_paper_sensor_unique_id_is_per_entry():
    assert PaperStatusSensor(_FakeEntry("a")).unique_id == "a_paper_status"  # type: ignore[arg-type]


async def test_adapter_get_paper_status_success():
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.paper_status.return_value = 1
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) == 1
    printer.close.assert_called_once()
    assert adapter.get_diagnostics()["paper_status"] == 1


async def test_adapter_get_paper_status_returns_none_on_error():
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))

    def _boom():
        raise OSError("unreachable")

    adapter._connect = _boom  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) is None
    assert adapter.get_diagnostics()["paper_status"] is None


async def test_adapter_get_paper_status_connect_failure_updates_diagnostics():
    """A connect failure during paper-status must not leave stale diagnostics.

    Regression: `get_paper_status` used to acquire via the bare
    `_acquire_printer`, whose connect-failure branch notified the
    connectivity sensor offline but never touched `_last_check` /
    `_last_error` / `_last_error_reason` -- those stayed at whatever an
    earlier successful operation last set them to.
    """
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))

    def _boom():
        raise OSError("unreachable")

    adapter._connect = _boom  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) is None
    diagnostics = adapter.get_diagnostics()
    assert diagnostics["last_check"] is not None
    assert diagnostics["last_error"] is not None
    assert diagnostics["last_error_reason"] == "connect failed"


async def test_adapter_get_paper_status_skips_when_print_in_flight():
    """A busy lock returns the last known value without touching the printer."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._last_paper_status = 2
    adapter._connect = MagicMock()  # type: ignore[method-assign]
    async with adapter._lock:
        assert await adapter.get_paper_status(_FakeHass()) == 2
    adapter._connect.assert_not_called()


async def test_cover_status_parsed_from_dle_eot_n2():
    """DLE EOT n=2 bit 2 (0x04) set means the cover is open."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()
    printer.paper_status.return_value = 2
    printer.query_status.return_value = b"\x16"
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) == 2
    assert await adapter.get_cover_status(_FakeHass()) is True
    printer.query_status.assert_called_with(b"\x10\x04\x02")


async def test_cover_status_empty_response_is_unknown():
    """A zero-length DLE EOT read means unknown, never 'closed'/OK."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()
    printer.paper_status.return_value = 2
    printer.query_status.return_value = b""
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is None


async def test_cover_status_query_error_is_unknown_but_paper_survives():
    """A cover-query failure must not clobber an otherwise-successful paper read."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()
    printer.paper_status.return_value = 1
    printer.query_status.side_effect = RuntimeError("no response")
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is None
    assert adapter._last_paper_status == 1


async def test_cover_status_cached_within_ttl():
    """A second get_cover_status call inside the TTL window reuses the cache."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.paper_status.return_value = 2
    printer.query_status.return_value = b"\x16"
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is True
    assert await adapter.get_cover_status(_FakeHass()) is True
    printer.query_status.assert_called_once()
