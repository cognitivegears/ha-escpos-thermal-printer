"""Tests for adapter lifecycle, status checking, and listeners.

Targets coverage for:
- network_adapter._status_check (success and failure paths, listener notification)
- base_adapter.start with keepalive=True
- base_adapter.async_request_status_check
- base_adapter._wrap_text
- base_adapter status listener add/remove
"""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass) -> MockConfigEntry:  # type: ignore[no-untyped-def]
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


async def test_status_check_success_updates_diagnostics(hass):  # type: ignore[no-untyped-def]
    """A successful status check should update last_check, last_ok, last_latency."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    # Patch socket.create_connection in the adapter module to simulate success.
    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    with patch(
        "custom_components.escpos_printer.printer.network_adapter.socket.create_connection",
        return_value=_FakeConn(),
    ):
        await adapter.async_request_status_check(hass)

    diag = adapter.get_diagnostics()
    assert diag["last_check"] is not None
    assert diag["last_ok"] is not None
    assert diag["last_latency_ms"] is not None
    assert diag["last_error_reason"] is None
    assert adapter.get_status() is True


async def test_status_check_failure_marks_offline_and_notifies(hass):  # type: ignore[no-untyped-def]
    """A failed status check should mark offline, set last_error, and notify listeners."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    received: list[bool] = []
    unsub = adapter.add_status_listener(received.append)

    # First, force a successful probe so status flips True -> later probes can flip back.
    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    with patch(
        "custom_components.escpos_printer.printer.network_adapter.socket.create_connection",
        return_value=_FakeConn(),
    ):
        await adapter.async_request_status_check(hass)

    # Then simulate a connection refusal.
    with patch(
        "custom_components.escpos_printer.printer.network_adapter.socket.create_connection",
        side_effect=OSError("Connection refused"),
    ):
        await adapter.async_request_status_check(hass)

    diag = adapter.get_diagnostics()
    assert diag["last_error"] is not None
    assert diag["last_error_reason"] is not None
    assert adapter.get_status() is False
    # Listener should have been notified at least once with False
    assert False in received

    unsub()


async def test_status_listener_unsubscribe(hass):  # type: ignore[no-untyped-def]
    """Unsubscribing a status listener should stop further callbacks."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    received: list[bool] = []
    unsub = adapter.add_status_listener(received.append)
    unsub()

    class _FakeConn:
        def __enter__(self): return self
        def __exit__(self, *_args): return False

    with patch(
        "custom_components.escpos_printer.printer.network_adapter.socket.create_connection",
        return_value=_FakeConn(),
    ):
        await adapter.async_request_status_check(hass)

    # Listener was unsubscribed before the probe — no callback expected
    assert received == []


async def test_unsubscribe_twice_is_safe(hass):  # type: ignore[no-untyped-def]
    """Unsubscribing the same listener twice should not raise."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    unsub = adapter.add_status_listener(lambda _: None)
    unsub()
    unsub()  # Should be a no-op, not raise


async def test_diagnostics_pre_setup_returns_initial_state(hass):  # type: ignore[no-untyped-def]
    """Adapter diagnostics before any status check returns None for all fields."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    diag = adapter.get_diagnostics()
    # No probe has run yet -> all timestamps are None
    assert diag["last_check"] is None
    assert diag["last_ok"] is None
    assert diag["last_error"] is None


async def test_wrap_text_respects_line_width(hass):  # type: ignore[no-untyped-def]
    """_wrap_text should wrap to the configured line width."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    # Set a small line width to force wrapping
    adapter._config.line_width = 10  # type: ignore[attr-defined]
    long_line = "abcdefghij klmnopqrst uvwxyz"
    wrapped = adapter._wrap_text(long_line)  # type: ignore[attr-defined]
    # Each output line must be at most 10 chars
    for line in wrapped.splitlines():
        assert len(line) <= 10, f"line too long: {line!r}"


async def test_wrap_text_zero_width_no_wrap(hass):  # type: ignore[no-untyped-def]
    """line_width=0 disables wrapping."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._config.line_width = 0  # type: ignore[attr-defined]

    text = "some long text that would normally be wrapped into multiple lines"
    assert adapter._wrap_text(text) == text  # type: ignore[attr-defined]


async def test_get_connection_info(hass):  # type: ignore[no-untyped-def]
    """Network adapter exposes a human-readable connection string."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    info = adapter.get_connection_info()
    assert "1.2.3.4" in info
    assert "9100" in info
