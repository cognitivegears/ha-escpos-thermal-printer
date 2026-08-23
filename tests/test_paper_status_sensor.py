"""Tests for the paper status sensor (issue #109)."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
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


class _YieldingHass:
    """Like _FakeHass, but actually suspends -- for exercising real interleaving."""

    async def async_add_executor_job(self, fn, *args):  # type: ignore[no-untyped-def]
        await asyncio.sleep(0)
        return fn(*args)


def _query_status_by_mode(
    *, paper: bytes = b"\x12", cover: bytes = b"\x12"
) -> Callable[[bytes], bytes]:
    """MagicMock side_effect: return different bytes per DLE EOT mode byte.

    Defaults are both "healthy" (paper ok, cover closed) so callers only
    need to override the mode they care about.
    """

    def _side_effect(mode: bytes) -> bytes:
        if mode == b"\x10\x04\x04":
            return paper
        if mode == b"\x10\x04\x02":
            return cover
        return b""

    return _side_effect


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
    printer.query_status.side_effect = _query_status_by_mode(paper=b"\x1e")  # near-end -> "low"
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) == 1
    printer.close.assert_called_once()
    assert adapter.get_diagnostics()["paper_status"] == 1


async def test_paper_status_empty_response_is_unknown():
    """A zero-length DLE EOT read means unknown, never a false 'ok' (python-escpos's default)."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.query_status.return_value = b""
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) is None


async def test_paper_status_non_conformant_byte_is_unknown():
    """A reply missing the real-time-status byte's fixed bits (1 and 4) is unknown.

    Not just an empty read -- e.g. a null or stale/misaligned byte left over
    in a keepalive socket buffer must not fall through to a false "ok".
    """
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.query_status.return_value = b"\x00"
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) is None


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
    printer.query_status.side_effect = _query_status_by_mode(cover=b"\x16")
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) == 2
    assert await adapter.get_cover_status(_FakeHass()) is True
    printer.query_status.assert_called_with(b"\x10\x04\x02")


async def test_cover_status_empty_response_is_unknown():
    """A zero-length DLE EOT read means unknown, never 'closed'/OK."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()
    printer.query_status.return_value = b""
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is None
    assert adapter._last_paper_status is None


async def test_cover_status_non_conformant_byte_is_unknown():
    """A garbage byte (e.g. 0xFF) must not fire a false PROBLEM alarm."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()
    printer.query_status.side_effect = _query_status_by_mode(cover=b"\xff")
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is None


async def test_cover_status_query_error_is_unknown_but_paper_survives():
    """A cover-query failure must not clobber an otherwise-successful paper read."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()

    def _side_effect(mode: bytes) -> bytes:
        if mode == b"\x10\x04\x04":
            return b"\x1e"  # near-end sensor -> "low"
        raise RuntimeError("no response")

    printer.query_status.side_effect = _side_effect
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is None
    assert adapter._last_paper_status == 1


async def test_paper_status_query_error_is_unknown_but_cover_survives():
    """A paper-query failure must not clobber an otherwise-successful cover read."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._status_query_ttl = 0
    printer = MagicMock()

    def _side_effect(mode: bytes) -> bytes:
        if mode == b"\x10\x04\x02":
            return b"\x16"  # cover open
        raise RuntimeError("no response")

    printer.query_status.side_effect = _side_effect
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_paper_status(_FakeHass()) is None
    assert adapter._last_cover_status is True


async def test_cover_status_cached_within_ttl():
    """A second get_cover_status call inside the TTL window reuses the cache."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.query_status.side_effect = _query_status_by_mode(cover=b"\x16")
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is True
    assert await adapter.get_cover_status(_FakeHass()) is True
    # One paper + one cover query on the first call; the second is a cache hit.
    assert printer.query_status.call_count == 2


async def test_cover_status_reflected_in_diagnostics():
    """get_diagnostics()['cover_open'] reflects _last_cover_status after a poll."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.query_status.side_effect = _query_status_by_mode(cover=b"\x16")
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    assert await adapter.get_cover_status(_FakeHass()) is True
    assert adapter.get_diagnostics()["cover_open"] is True


async def test_adapter_get_cover_status_skips_when_print_in_flight():
    """A busy lock returns the last known cover value without opening a connection."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    adapter._last_cover_status = False
    adapter._connect = MagicMock()  # type: ignore[method-assign]
    async with adapter._lock:
        assert await adapter.get_cover_status(_FakeHass()) is False
    adapter._connect.assert_not_called()


async def test_concurrent_status_polls_share_one_query_round_trip():
    """The paper sensor and cover sensor poll concurrently at setup/on-cadence.

    Regression: the freshness-guard TTL check lived *inside*
    ``_probe_lock_or_skip``'s hold of the print-serializing lock, so the
    loser of the race saw that lock already held (by the winner's in-flight
    query) and took the "print in flight" skip path -- reading a cache that
    was still empty, instead of waiting for the winner's fresh result.
    """
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    printer.query_status.side_effect = _query_status_by_mode(paper=b"\x1e", cover=b"\x16")
    adapter._connect = lambda: printer  # type: ignore[method-assign]

    hass = _YieldingHass()
    paper_result, cover_result = await asyncio.gather(
        adapter.get_paper_status(hass), adapter.get_cover_status(hass)
    )
    assert paper_result == 1
    assert cover_result is True
    # Exactly one round trip: the second (losing) caller must reuse the
    # freshly-populated cache, not re-query or read a stale/empty one.
    assert printer.query_status.call_count == 2
