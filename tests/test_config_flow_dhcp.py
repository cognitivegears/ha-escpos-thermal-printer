"""DHCP discovery flow tests."""

from __future__ import annotations

from unittest.mock import ANY, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN

DISCOVERY = DhcpServiceInfo(
    ip="192.168.10.157",
    hostname="TM-T20II-628E52",
    macaddress="50579c628e52",
)

# "tm-*" also matches Prometheus node_exporter's default port 9100, so
# hostname-fallback (no GS I answer) title tests use a brand-exclusive
# "rongta_*" hostname instead -- port-probe-only identification still
# applies there.
DISCOVERY_RONGTA = DhcpServiceInfo(
    ip="192.168.10.158",
    hostname="Rongta_RP820",
    macaddress="50579c628e53",
)


async def _start_dhcp_flow(hass, can_connect=True, query_result=None, discovery=DISCOVERY):
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
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=discovery
        )


async def test_dhcp_discovery_shows_network_form(hass):
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "network"
    # Host is prefilled from discovery.
    host_marker = next(k for k in result["data_schema"].schema if k.schema == "host")
    assert host_marker.description["suggested_value"] == "192.168.10.157"


async def test_dhcp_discovery_preselects_suggested_profile(hass):
    with patch(
        "custom_components.escpos_printer._config_flow.network_steps.suggest_profile",
        return_value="TM-T20II",
    ):
        result = await _start_dhcp_flow(hass, query_result={"model": "TM-T20II"})
    assert result["step_id"] == "network"
    defaults = result["data_schema"]({"host": "192.168.10.157"})
    assert defaults["profile"] == "TM-T20II"


async def test_dhcp_discovery_unknown_model_keeps_auto_profile(hass):
    from custom_components.escpos_printer.capabilities import PROFILE_AUTO

    result = await _start_dhcp_flow(hass, query_result={"model": "Mystery-9000"})
    defaults = result["data_schema"]({"host": "192.168.10.157"})
    assert defaults["profile"] == PROFILE_AUTO


async def test_dhcp_discovery_title_uses_detected_model(hass):
    await _start_dhcp_flow(hass, query_result={"model": "TM-T20II"})
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {"name": "TM-T20II (192.168.10.157)"}


async def test_dhcp_discovery_title_falls_back_to_hostname(hass):
    # rongta_* is brand-exclusive, so a silent GS I query still shows a
    # discovery card with the hostname as the fallback title.
    await _start_dhcp_flow(hass, query_result=None, discovery=DISCOVERY_RONGTA)
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {"name": "Rongta_RP820 (192.168.10.158)"}


async def test_dhcp_discovery_tm_hostname_aborts_without_gs_i_answer(hass):
    """tm-* also matches node_exporter's default port 9100 -- a silent GS I
    query must abort instead of showing a bogus discovery card."""
    result = await _start_dhcp_flow(hass, can_connect=True, query_result=None)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_discovery_aborts_when_port_closed(hass):
    result = await _start_dhcp_flow(hass, can_connect=False)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_dhcp_discovery_edited_host_requeries_instead_of_reusing_detection(hass):
    """Editing the suggested host to a different printer must not carry over
    the discovery-time GS I result for the original printer."""
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result["step_id"] == "network"

    edited_host = "192.168.10.200"
    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value={"manufacturer": "OTHER", "model": "RP820"},
        ) as mock_query,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": edited_host, "port": 9100}
        )
        # Complete the codepage step with defaults to create the entry.
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["detected_manufacturer"] == "OTHER"
    assert result["data"]["detected_model"] == "RP820"
    mock_query.assert_called_once_with(edited_host, 9100, ANY)


async def test_dhcp_discovery_aborts_when_already_configured(hass):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9100",
        data={"connection_type": "network", "host": "192.168.10.157", "port": 9100},
    ).add_to_hass(hass)
    result = await _start_dhcp_flow(hass)
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_discovery_end_to_end_creates_entry_with_detection(hass):
    """DHCP discovery -> network form, submitted with the unchanged
    suggested host, creates an entry carrying the GS I detection and the
    preselected profile."""
    with patch(
        "custom_components.escpos_printer._config_flow.network_steps.suggest_profile",
        return_value="TM-T20II",
    ):
        result = await _start_dhcp_flow(
            hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
        )
        assert result["step_id"] == "network"
        assert result["data_schema"]({"host": "192.168.10.157"})["profile"] == "TM-T20II"

        with patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ):
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"host": "192.168.10.157", "port": 9100}
            )
            # Complete the codepage step with defaults to create the entry.
            result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["detected_manufacturer"] == "EPSON"
    assert result["data"]["detected_model"] == "TM-T20II"
    assert result["data"]["profile"] == "TM-T20II"


async def test_dhcp_discovery_duplicate_in_progress_aborts(hass):
    """A second DHCP discovery for the same IP while the first flow is
    still open (unanswered form) aborts as already_in_progress."""
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result["type"] == FlowResultType.FORM

    result2 = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "already_in_progress"
