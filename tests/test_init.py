"""Tests for integration setup and unload lifecycle."""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer import (
    DATA_SERVICES_REGISTERED,
    EscposRuntimeData,
)
from custom_components.escpos_printer.const import (
    CONF_BT_MAC,
    CONF_CONNECTION_TYPE,
    CONF_SERIAL_PORT,
    CONF_STATUS_INTERVAL,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_SERIAL,
    DOMAIN,
)


def _make_entry(host: str = "1.2.3.4", port: int = 9100) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title=f"{host}:{port}",
        data={CONF_HOST: host, CONF_PORT: port},
        unique_id=f"{host}:{port}",
    )


async def test_setup_assigns_runtime_data(hass):  # type: ignore[no-untyped-def]
    """async_setup_entry must populate entry.runtime_data with adapter + defaults."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert isinstance(entry.runtime_data, EscposRuntimeData)
    assert entry.runtime_data.adapter is not None
    assert "align" in entry.runtime_data.defaults
    assert "cut" in entry.runtime_data.defaults
    # Secure-by-default: the SSRF opt-in is off unless the option is set.
    assert entry.runtime_data.adapter.allow_local_image_urls is False


async def test_setup_propagates_allow_local_image_urls_option(hass):  # type: ignore[no-untyped-def]
    """The allow-local option must reach the adapter so the resolver relaxes."""
    from custom_components.escpos_printer.const import CONF_ALLOW_LOCAL_IMAGE_URLS

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        options={CONF_ALLOW_LOCAL_IMAGE_URLS: True},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.adapter.allow_local_image_urls is True


async def test_setup_registers_global_services_once(hass):  # type: ignore[no-untyped-def]
    """Services should be registered exactly once on first entry setup."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.data[DOMAIN][DATA_SERVICES_REGISTERED] is True
    # Spot-check that representative services are registered
    assert hass.services.has_service(DOMAIN, "print_text")
    assert hass.services.has_service(DOMAIN, "print_qr")
    assert hass.services.has_service(DOMAIN, "feed")
    assert hass.services.has_service(DOMAIN, "cut")


async def test_unload_last_entry_tears_down_services(hass):  # type: ignore[no-untyped-def]
    """When the last loaded entry unloads, global services must deregister."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert hass.services.has_service(DOMAIN, "print_text")

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert hass.data[DOMAIN][DATA_SERVICES_REGISTERED] is False
    assert not hass.services.has_service(DOMAIN, "print_text")


async def test_unload_one_of_two_entries_keeps_services(hass):  # type: ignore[no-untyped-def]
    """While at least one entry is still loaded, services must remain registered."""
    from homeassistant.config_entries import ConfigEntryState

    e1 = _make_entry("1.1.1.1", 9100)
    e2 = _make_entry("2.2.2.2", 9100)
    e1.add_to_hass(hass)
    e2.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        # async_setup() of the first entry triggers integration setup, which
        # then loads all not-yet-loaded entries for the domain. Only call
        # async_setup explicitly for entries still in NOT_LOADED state.
        assert await hass.config_entries.async_setup(e1.entry_id)
        await hass.async_block_till_done()
        if e2.state is ConfigEntryState.NOT_LOADED:
            assert await hass.config_entries.async_setup(e2.entry_id)
            await hass.async_block_till_done()

        assert e1.state is ConfigEntryState.LOADED
        assert e2.state is ConfigEntryState.LOADED
        assert hass.services.has_service(DOMAIN, "print_text")

        assert await hass.config_entries.async_unload(e1.entry_id)
        await hass.async_block_till_done()

    # e2 is still loaded — services must persist
    assert hass.data[DOMAIN][DATA_SERVICES_REGISTERED] is True
    assert hass.services.has_service(DOMAIN, "print_text")


async def test_unload_calls_adapter_stop(hass):  # type: ignore[no-untyped-def]
    """async_unload_entry must call adapter.stop() on the entry's adapter."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        adapter = entry.runtime_data.adapter
        with patch.object(adapter, "stop", wraps=adapter.stop) as stop_spy:
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()
            stop_spy.assert_called_once()


async def test_unload_logs_adapter_stop_failure(hass, caplog):  # type: ignore[no-untyped-def]
    """A failing adapter.stop() during unload must leave a debug-level trace.

    Regression: async_unload_entry used to silently `pass` on any
    exception from adapter.stop(), leaving no trace of a hung close.
    """
    import logging

    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        adapter = entry.runtime_data.adapter
        with (
            patch.object(adapter, "stop", side_effect=RuntimeError("boom")),
            caplog.at_level(logging.DEBUG, logger="custom_components.escpos_printer"),
        ):
            assert await hass.config_entries.async_unload(entry.entry_id)
            await hass.async_block_till_done()

    assert any(
        "Adapter stop failed" in rec.message and "boom" in rec.message for rec in caplog.records
    )


async def test_setup_serial_status_interval_defaults_to_300(hass):  # type: ignore[no-untyped-def]
    """A serial entry with no stored status_interval option gets a 300s default.

    Serial/Bluetooth printers get no implicit health check from the paper
    poll (network/USB only), so an unplugged printer would otherwise stay
    "Online" forever with the old always-0 default.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serial Printer",
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        },
        unique_id="serial:/dev/ttyUSB0",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.adapter._status_interval == 300

    # Explicit teardown so the recurring status-check timer this test
    # schedules (status_interval=300) doesn't outlive the test.
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_setup_serial_status_interval_explicit_zero_respected(hass):  # type: ignore[no-untyped-def]
    """An explicit status_interval=0 option overrides the serial/BT default."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serial Printer",
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
        },
        options={CONF_STATUS_INTERVAL: 0},
        unique_id="serial:/dev/ttyUSB0",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.runtime_data.adapter._status_interval == 0


async def test_setup_bluetooth_status_interval_still_defaults_to_0(hass):  # type: ignore[no-untyped-def]
    """A Bluetooth entry with no stored status_interval option stays at 0.

    Unlike serial, Bluetooth status checks open a real RFCOMM connection and
    many cheap printers audibly beep on every connect, so polling stays
    opt-in rather than defaulting on.

    The adapter factory is mocked out here (rather than doing a full
    real-transport setup like the serial test above) so this only exercises
    the connection-type default computation in async_setup_entry. The
    battery sensor's bluez lookup is also mocked -- it otherwise attempts a
    real D-Bus system-bus connect during platform forwarding (harmlessly
    caught by bluez.py, but pytest-socket still flags the blocked attempt).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer",
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
        },
        unique_id="bt:AA:BB:CC:DD:EE:FF",
    )
    entry.add_to_hass(hass)
    fake_adapter = MagicMock()
    fake_adapter.start = AsyncMock()
    fake_adapter.stop = AsyncMock()

    with (
        patch("custom_components.escpos_printer.create_printer_adapter", return_value=fake_adapter),
        patch(
            "custom_components.escpos_printer.sensor.query_bt_battery_percentage",
            AsyncMock(return_value=None),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    fake_adapter.start.assert_called_once()
    assert fake_adapter.start.call_args.kwargs["status_interval"] == 0


async def test_setup_network_status_interval_still_defaults_to_0(hass):  # type: ignore[no-untyped-def]
    """Network/USB printers keep the old 0 (disabled) default -- unaffected."""
    entry = _make_entry()
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.runtime_data.adapter._status_interval == 0
