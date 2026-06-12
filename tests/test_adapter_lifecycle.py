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
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

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
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

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
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

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


async def test_get_profile_pixel_width_handles_broken_profile_data(hass):  # type: ignore[no-untyped-def]
    """A configured profile missing the media/width keys must not raise.

    Exercises the AttributeError/KeyError/TypeError/ValueError guard in
    get_profile_pixel_width: a profile object with malformed profile_data
    falls back to None rather than crashing the image pipeline. The width
    is read from the configured profile object (``_get_profile_obj``),
    not the live connection — the connection is None for USB/Bluetooth
    and non-keepalive network printers.
    """
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    class _BrokenProfile:
        # Real dict so ["media"] raises KeyError (not a Mock that auto-vivifies).
        profile_data: dict = {}

    # Class is callable with no args → returns a fresh instance, matching
    # the _get_profile_obj() contract.
    adapter._get_profile_obj = _BrokenProfile  # type: ignore[attr-defined,method-assign]
    # No hass passed → skips the repair-issue path; just exercises the guard.
    assert adapter.get_profile_pixel_width() is None


async def test_get_profile_pixel_width_reads_configured_profile(hass):  # type: ignore[no-untyped-def]
    """A profile that declares media.width.pixels is read without a connection."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    class _Profile:
        profile_data = {"media": {"width": {"pixels": 576}}}

    adapter._get_profile_obj = _Profile  # type: ignore[attr-defined,method-assign]
    # self._printer is None (no keepalive), proving the width comes from
    # the profile object, not the connection.
    assert adapter._printer is None  # type: ignore[attr-defined]
    assert adapter.get_profile_pixel_width() == 576


async def test_get_profile_pixel_width_auto_profile_silent_fallback(hass, caplog):  # type: ignore[no-untyped-def]
    """The auto/default profile (no profile chosen) falls back silently."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    # Auto profile → _get_profile_obj() returns None → fallback with no
    # warning and no repair issue (it's expected, not a misconfiguration).
    adapter._get_profile_obj = lambda: None  # type: ignore[attr-defined,method-assign]
    assert adapter.get_profile_pixel_width(hass) is None
    assert not any(
        "does not expose media.width.pixels" in rec.message for rec in caplog.records
    )


async def test_get_connection_info(hass):  # type: ignore[no-untyped-def]
    """Network adapter exposes a human-readable connection string."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    info = adapter.get_connection_info()
    assert "1.2.3.4" in info
    assert "9100" in info


async def test_network_status_check_skips_when_lock_held(hass):  # type: ignore[no-untyped-def]
    """T-M1 / P-M2: network adapter must not probe while a print holds the lock.

    Opening a second TCP connection mid-print can flap bandwidth-
    constrained transports (Bluetooth/USB-IP via TCP gateway). The
    sensor stays at its last-known value rather than corrupting an
    active job.
    """
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    prior_check = adapter._last_check  # type: ignore[attr-defined]
    prior_status = adapter.get_status()

    async with adapter._lock:  # type: ignore[attr-defined]
        # If the lock-skip is dropped, this would attempt a real socket
        # connect and either succeed (mutating _last_check) or fail
        # (mutating _last_error). Either mutation fails the assertion.
        await adapter._status_check(hass)  # type: ignore[attr-defined]

    assert adapter._last_check is prior_check  # type: ignore[attr-defined]
    assert adapter.get_status() is prior_status
