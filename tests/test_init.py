"""Tests for integration setup and unload lifecycle."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer import (
    DATA_SERVICES_REGISTERED,
    EscposRuntimeData,
)
from custom_components.escpos_printer.const import DOMAIN


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
