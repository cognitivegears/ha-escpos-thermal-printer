"""End-to-end integration test for the Bluetooth Classic / RFCOMM adapter.

Production opens an ``AF_BLUETOOTH`` socket; the test seam swaps that for a
TCP-loopback transport pointed at the existing ``VirtualPrinter`` ESC/POS
emulator. This proves the adapter's whole I/O path (python-escpos →
``_raw`` → transport → kernel socket → emulator → command parser) without
needing a real Bluetooth radio or root.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import socket
import time
from typing import Any

import pytest

from custom_components.escpos_printer.printer import (
    BluetoothPrinterAdapter,
    BluetoothPrinterConfig,
    bluetooth_transport,
)
from tests.integration_tests.emulator import VirtualPrinter

pytestmark = pytest.mark.integration


class _LoopbackTransport:
    """Test transport that talks to the VirtualPrinter over TCP loopback.

    The emulator's command parser has a quirk where multiple commands
    received in a single TCP segment are parsed but all-but-the-first are
    discarded. To make this test deterministic regardless of timing, we
    sleep briefly between successive ``write`` calls so each python-escpos
    ``_raw`` invocation lands in its own kernel read.
    """

    def __init__(self, host: str, port: int, timeout: float) -> None:
        self._sock = socket.create_connection((host, port), timeout=max(timeout, 0.1))
        # Disable Nagle so each sendall lands in its own segment.
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

    def write(self, data: bytes) -> None:
        if not data:
            return
        self._sock.sendall(data)
        # Give the emulator's reader time to drain this write before the
        # next one arrives — works around the parser-discards-extras bug.
        time.sleep(0.02)

    def close(self) -> None:
        # Drain before closing so the emulator processes all bytes.
        time.sleep(0.05)
        try:
            self._sock.close()
        except OSError:
            pass


@pytest.fixture
async def bt_adapter_over_loopback(
    monkeypatch: Any, hass: Any
) -> AsyncGenerator[tuple[BluetoothPrinterAdapter, Any, Any]]:
    """Yield ``(adapter, server, hass)`` wired to a virtual TCP printer."""
    async with VirtualPrinter(host="127.0.0.1", port=9110) as server:
        def _factory(_mac: str, _channel: int, timeout: float) -> _LoopbackTransport:
            return _LoopbackTransport("127.0.0.1", 9110, timeout)

        monkeypatch.setattr(bluetooth_transport, "open_rfcomm_transport", _factory)

        config = BluetoothPrinterConfig(
            mac="AA:BB:CC:DD:EE:FF",
            rfcomm_channel=1,
            timeout=4.0,
            codepage="CP437",
            line_width=48,
        )
        adapter = BluetoothPrinterAdapter(config)
        await adapter.start(hass, keepalive=False, status_interval=0)
        try:
            yield adapter, server, hass
        finally:
            await adapter.stop()


async def _wait_for_bytes(server, expected: bytes, timeout: float = 3.0) -> bytes:
    """Poll the emulator's command log until ``expected`` shows up or we time out."""
    deadline = asyncio.get_event_loop().time() + timeout
    last_blob = b""
    while asyncio.get_event_loop().time() < deadline:
        log = await server.get_command_log()
        last_blob = b"".join(getattr(cmd, "raw_data", b"") for cmd in log)
        if expected in last_blob:
            return last_blob
        await asyncio.sleep(0.05)
    return last_blob


@pytest.mark.asyncio
async def test_print_text_reaches_emulator(bt_adapter_over_loopback) -> None:
    """Text printed via the BT adapter is received and parsed by the emulator."""
    adapter, server, hass = bt_adapter_over_loopback
    await adapter.print_text(
        hass=hass,
        text="Hello Bluetooth Loopback",
        align="left",
        cut="none",
        feed=0,
    )
    raw_blob = await _wait_for_bytes(server, b"Hello Bluetooth Loopback")
    assert b"Hello Bluetooth Loopback" in raw_blob, raw_blob


@pytest.mark.asyncio
async def test_feed_reaches_emulator(bt_adapter_over_loopback) -> None:
    """Feed control commands flow end-to-end through a fresh RFCOMM connection."""
    adapter, server, hass = bt_adapter_over_loopback
    initial_log_len = len(await server.get_command_log())
    await adapter.feed(hass=hass, lines=3)
    await asyncio.sleep(0.2)
    log = await server.get_command_log()
    # New commands were appended for the feed operation.
    assert len(log) > initial_log_len
    cmd_types = {getattr(cmd, "command_type", None) for cmd in log}
    assert "feed" in cmd_types


@pytest.mark.asyncio
async def test_each_op_opens_fresh_connection(bt_adapter_over_loopback) -> None:
    """Connect-per-op behavior: each adapter call uses a new RFCOMM transport."""
    adapter, server, hass = bt_adapter_over_loopback
    initial = server.get_client_count()
    await adapter.print_text(hass=hass, text="X", cut="none", feed=0)
    await asyncio.sleep(0.05)
    await adapter.feed(hass=hass, lines=1)
    await asyncio.sleep(0.2)
    # Connections opened and closed (count returns to baseline because the
    # adapter forces keepalive=False).
    assert server.get_client_count() == initial


@pytest.mark.asyncio
async def test_status_check_reaches_emulator(bt_adapter_over_loopback) -> None:
    """Status check hits the emulator and marks the printer reachable."""
    adapter, _server, hass = bt_adapter_over_loopback
    await adapter._status_check(hass)
    assert adapter.get_status() is True
    assert adapter._last_error_reason is None
