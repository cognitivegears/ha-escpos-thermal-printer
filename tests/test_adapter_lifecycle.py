"""Tests for adapter lifecycle, status checking, and listeners.

Targets coverage for:
- network_adapter._status_check (success and failure paths, listener notification)
- base_adapter.start with keepalive=True
- base_adapter.async_request_status_check
- base_adapter._wrap_text
- base_adapter status listener add/remove
"""

from unittest.mock import MagicMock, patch

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


async def test_setup_runs_initial_probe_regardless_of_status_interval(hass):  # type: ignore[no-untyped-def]
    """start() always runs a one-shot probe, even with status_interval=0 (the default).

    Without this, entities that read get_status() at construction (the
    connectivity binary_sensor) saw ``None``/"unknown" until the first
    print. ``_setup_entry`` here uses the default status_interval=0, and
    the `fake_network_status_probe` fixture makes the network probe fail
    (no real socket access in unit tests) -- so diagnostics are already
    populated immediately after setup instead of sitting at "no probe has
    run yet". get_status() itself is no longer None (the point of this
    fix); its exact True/False value also reflects the paper-status
    sensor's own initial poll, so it isn't pinned down here.
    """
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    diag = adapter.get_diagnostics()
    assert diag["last_check"] is not None
    assert diag["last_error"] is not None
    assert adapter.get_status() is not None
    # The recurring timer itself is still gated by status_interval (0 here).
    assert adapter._cancel_status is None  # type: ignore[attr-defined]


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


async def test_wrap_text_preserves_trailing_newline(hass):  # type: ignore[no-untyped-def]
    """Wrapping must not strip a trailing newline.

    The calibration wizard's labels rely on the trailing ``\\n`` to
    flush the printer's line buffer before an image command (with
    ``feed=0`` nothing else terminates the line); ``splitlines()`` +
    ``join`` silently ate it, so the label was dropped/merged into the
    following image on real hardware (Ronga RP850P).
    """
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._config.line_width = 42  # type: ignore[attr-defined]

    assert adapter._wrap_text("TEST 1\n") == "TEST 1\n"  # type: ignore[attr-defined]
    assert adapter._wrap_text("a\n\n") == "a\n\n"  # type: ignore[attr-defined]
    assert adapter._wrap_text("no newline") == "no newline"  # type: ignore[attr-defined]


async def test_wrap_text_zero_width_no_wrap(hass):  # type: ignore[no-untyped-def]
    """line_width=0 disables wrapping."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._config.line_width = 0  # type: ignore[attr-defined]

    text = "some long text that would normally be wrapped into multiple lines"
    assert adapter._wrap_text(text) == text  # type: ignore[attr-defined]


async def test_print_text_wrap_false_skips_wrapping(hass):  # type: ignore[no-untyped-def]
    """print_text(wrap=False) sends the text unwrapped even with a configured line_width."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._config.line_width = 10  # type: ignore[attr-defined]

    long_line = "abcdefghij klmnopqrst uvwxyz"
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await adapter.print_text(hass, text=long_line, wrap=False)
    fake.text.assert_called_once_with(long_line)


async def test_print_text_wrap_default_true_wraps(hass):  # type: ignore[no-untyped-def]
    """print_text's default (wrap unset) keeps today's wrapping behavior."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._config.line_width = 10  # type: ignore[attr-defined]

    long_line = "abcdefghij klmnopqrst uvwxyz"
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await adapter.print_text(hass, text=long_line)
    fake.text.assert_called_once()
    printed = fake.text.call_args.args[0]
    assert printed != long_line
    for line in printed.splitlines():
        assert len(line) <= 10


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
    assert not any("does not expose media.width.pixels" in rec.message for rec in caplog.records)


async def test_profile_width_repair_issue_is_scoped_per_entry(hass):  # type: ignore[no-untyped-def]
    """Two entries with the same broken profile must not share one issue id.

    Regression: the issue id used to be keyed by profile *name* only, so
    entry A "fixing" its profile would delete entry B's still-broken
    warning too.
    """
    from homeassistant.helpers import issue_registry as ir

    from custom_components.escpos_printer.const import DOMAIN

    class _BrokenProfile:
        profile_data: dict = {}

    entry_a = await _setup_entry(hass)
    adapter_a = entry_a.runtime_data.adapter
    adapter_a._get_profile_obj = _BrokenProfile  # type: ignore[attr-defined,method-assign]
    adapter_a.get_profile_pixel_width(hass)

    entry_b = MockConfigEntry(
        domain=DOMAIN,
        title="5.6.7.8:9100",
        data={CONF_HOST: "5.6.7.8", CONF_PORT: 9100},
        unique_id="5.6.7.8:9100",
    )
    entry_b.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry_b.entry_id)
        await hass.async_block_till_done()
    adapter_b = entry_b.runtime_data.adapter
    adapter_b._get_profile_obj = _BrokenProfile  # type: ignore[attr-defined,method-assign]
    adapter_b.get_profile_pixel_width(hass)

    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(DOMAIN, f"profile_width_fallback_{entry_a.entry_id}") is not None
    )
    assert (
        registry.async_get_issue(DOMAIN, f"profile_width_fallback_{entry_b.entry_id}") is not None
    )


async def test_profile_width_repair_issue_cleared_once_profile_resolves(hass):  # type: ignore[no-untyped-def]
    """The fallback issue must not outlive a profile fix (reload)."""
    from homeassistant.helpers import issue_registry as ir

    from custom_components.escpos_printer.const import DOMAIN

    class _BrokenProfile:
        profile_data: dict = {}

    class _GoodProfile:
        profile_data = {"media": {"width": {"pixels": 576}}}

    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._get_profile_obj = _BrokenProfile  # type: ignore[attr-defined,method-assign]
    adapter.get_profile_pixel_width(hass)

    registry = ir.async_get(hass)
    issue_id = f"profile_width_fallback_{entry.entry_id}"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    # Simulate a reload with a fresh adapter instance (real reload behavior)
    # whose profile now resolves cleanly.
    new_adapter = entry.runtime_data.adapter.__class__(adapter.config)
    new_adapter.entry_id = entry.entry_id
    new_adapter._get_profile_obj = _GoodProfile  # type: ignore[attr-defined,method-assign]
    assert new_adapter.get_profile_pixel_width(hass) == 576

    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_profile_width_repair_issue_clears_legacy_profile_scoped_id(hass):  # type: ignore[no-untyped-def]
    """Resolving the profile must also delete the pre-1.0 profile-name-scoped issue id.

    Pre-1.0, the repair-issue id was keyed by profile *name* rather than
    entry id; an install upgrading from that era could still have one of
    those legacy issues sitting in the registry after the profile is
    fixed. ``_clear_profile_width_repair_issue`` must delete both ids.
    """
    from homeassistant.helpers import issue_registry as ir

    from custom_components.escpos_printer.const import DOMAIN

    class _GoodProfile:
        profile_data = {"media": {"width": {"pixels": 576}}}

    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter.config.profile = "TM-T88V"

    registry = ir.async_get(hass)
    legacy_issue_id = "profile_width_fallback_TM-T88V"
    ir.async_create_issue(
        hass,
        DOMAIN,
        legacy_issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="profile_width_fallback",
        translation_placeholders={"profile": "TM-T88V", "fallback": "384"},
    )
    assert registry.async_get_issue(DOMAIN, legacy_issue_id) is not None

    adapter._get_profile_obj = _GoodProfile  # type: ignore[attr-defined,method-assign]
    assert adapter.get_profile_pixel_width(hass) == 576

    assert registry.async_get_issue(DOMAIN, legacy_issue_id) is None


async def test_async_remove_entry_deletes_repair_issue(hass):  # type: ignore[no-untyped-def]
    """Removing the config entry must clean up its repair issue too."""
    from homeassistant.helpers import issue_registry as ir

    from custom_components.escpos_printer import async_remove_entry
    from custom_components.escpos_printer.const import DOMAIN

    class _BrokenProfile:
        profile_data: dict = {}

    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._get_profile_obj = _BrokenProfile  # type: ignore[attr-defined,method-assign]
    adapter.get_profile_pixel_width(hass)

    registry = ir.async_get(hass)
    issue_id = f"profile_width_fallback_{entry.entry_id}"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    await async_remove_entry(hass, entry)

    assert registry.async_get_issue(DOMAIN, issue_id) is None


async def test_width_pixels_override_clears_existing_repair_issue(hass):  # type: ignore[no-untyped-def]
    """A user-set width_pixels override must beat a broken profile AND
    delete the fallback repairs issue that broken profile filed.
    """
    from homeassistant.helpers import issue_registry as ir

    from custom_components.escpos_printer.const import DOMAIN

    class _BrokenProfile:
        profile_data: dict = {}

    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter
    adapter._get_profile_obj = _BrokenProfile  # type: ignore[attr-defined,method-assign]
    adapter.get_profile_pixel_width(hass)

    registry = ir.async_get(hass)
    issue_id = f"profile_width_fallback_{entry.entry_id}"
    assert registry.async_get_issue(DOMAIN, issue_id) is not None

    adapter.config.width_pixels = 640
    assert adapter.get_profile_pixel_width(hass) == 640
    assert registry.async_get_issue(DOMAIN, issue_id) is None


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


async def test_batch_connection_uses_one_connection_for_the_whole_page(hass):  # type: ignore[no-untyped-def]
    """batch_connection: all prints ride one connection, closed once at the end.

    The reconnect-per-operation model sends each print on its own TCP
    connection; printers that accept the next connection before the
    previous buffer drains can reorder the fragments on paper (seen on
    TM-T20II during calibration). One page = one connection is the fix.
    """
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    fake_printer = MagicMock()
    with patch.object(adapter, "_connect", return_value=fake_printer) as connect:
        async with adapter.batch_connection(hass) as page:
            await page.print_text(text="TEST 1\n")
            await page.print_text(text="TEST 2\n")
            await page.feed(5)

    assert connect.call_count == 1
    assert fake_printer.close.call_count == 1
    assert [c.args[0] for c in fake_printer.text.call_args_list] == ["TEST 1\n", "TEST 2\n"]
    fake_printer.ln.assert_called_once_with(5)
    assert adapter.get_status() is True


async def test_batch_connection_failure_closes_connection_and_marks_offline(hass):  # type: ignore[no-untyped-def]
    """An exception escaping the batch releases the connection with failed=True."""
    import pytest

    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    fake_printer = MagicMock()
    with (
        patch.object(adapter, "_connect", return_value=fake_printer),
        pytest.raises(RuntimeError),
    ):
        async with adapter.batch_connection(hass):
            raise RuntimeError("boom")

    assert fake_printer.close.call_count == 1
    assert adapter.get_status() is False
