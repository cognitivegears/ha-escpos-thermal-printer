"""Tests for diagnostics.py."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONF_IN_EP,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_USB,
    DOMAIN,
)
from custom_components.escpos_printer.diagnostics import (
    async_get_config_entry_diagnostics,
)


async def test_diagnostics_network_entry(hass):  # type: ignore[no-untyped-def]
    """Diagnostics for a fully-set-up network entry should populate runtime data."""
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

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["title"] == "1.2.3.4:9100"
    # Host is redacted
    assert diag["entry"]["data"][CONF_HOST] == "**REDACTED**"
    assert diag["entry"]["data"][CONF_PORT] == 9100
    # Runtime contains adapter-derived fields
    assert diag["runtime"]["connection_type"] == CONNECTION_TYPE_NETWORK
    assert "profile" in diag["runtime"]
    assert "codepage" in diag["runtime"]
    assert "line_width" in diag["runtime"]
    # Network-specific runtime fields
    assert diag["runtime"]["host"] == "**REDACTED**"
    assert diag["runtime"]["port"] == 9100


async def test_diagnostics_usb_entry(hass):  # type: ignore[no-untyped-def]
    """Diagnostics for a USB entry should include VID/PID/endpoint info."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer",
        data={
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0E03,
            CONF_IN_EP: 0x82,
            CONF_OUT_EP: 0x01,
        },
        unique_id="usb:04B8:0E03",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Usb"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)

    assert diag["entry"]["data"][CONF_CONNECTION_TYPE] == CONNECTION_TYPE_USB
    assert diag["entry"]["data"][CONF_VENDOR_ID] == "0x04B8"
    assert diag["entry"]["data"][CONF_PRODUCT_ID] == "0x0E03"
    assert diag["entry"]["data"][CONF_IN_EP] == "0x82"
    assert diag["entry"]["data"][CONF_OUT_EP] == "0x01"
    # Runtime USB-specific fields
    assert diag["runtime"]["connection_type"] == CONNECTION_TYPE_USB
    assert diag["runtime"]["vendor_id"] == "0x04B8"
    assert diag["runtime"]["product_id"] == "0x0E03"


async def test_diagnostics_without_runtime_data(hass):  # type: ignore[no-untyped-def]
    """Diagnostics must work even when runtime_data hasn't been set (e.g. setup failed)."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
    )
    # Note: NOT calling async_setup, so runtime_data is unset.
    entry.add_to_hass(hass)

    diag = await async_get_config_entry_diagnostics(hass, entry)

    # Entry section is still populated from the static data
    assert diag["entry"]["title"] == "1.2.3.4:9100"
    assert diag["entry"]["data"][CONF_PORT] == 9100
    # Runtime section is empty because no adapter exists
    assert diag["runtime"] == {}
