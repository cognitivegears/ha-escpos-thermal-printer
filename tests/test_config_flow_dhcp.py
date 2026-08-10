"""DHCP discovery flow tests."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN

DISCOVERY = DhcpServiceInfo(
    ip="192.168.10.157",
    hostname="TM-T20II-628E52",
    macaddress="50579c628e52",
)


async def _start_dhcp_flow(hass, can_connect=True, query_result=None):
    with (
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps._can_connect",
            return_value=can_connect,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps.query_printer_id",
            return_value=query_result,
        ),
    ):
        return await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DISCOVERY
        )


@pytest.mark.xfail(reason="host prefill lands in next task", strict=True)
async def test_dhcp_discovery_shows_network_form(hass):
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "network"
    # Host is prefilled from discovery.
    assert result["data_schema"]({})["host"] == "192.168.10.157"


async def test_dhcp_discovery_title_uses_detected_model(hass):
    await _start_dhcp_flow(hass, query_result={"model": "TM-T20II"})
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {"name": "TM-T20II (192.168.10.157)"}


async def test_dhcp_discovery_title_falls_back_to_hostname(hass):
    await _start_dhcp_flow(hass, query_result=None)
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {
        "name": "TM-T20II-628E52 (192.168.10.157)"
    }


async def test_dhcp_discovery_aborts_when_port_closed(hass):
    result = await _start_dhcp_flow(hass, can_connect=False)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_discovery_aborts_when_already_configured(hass):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9100",
        data={"connection_type": "network", "host": "192.168.10.157", "port": 9100},
    ).add_to_hass(hass)
    result = await _start_dhcp_flow(hass)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
