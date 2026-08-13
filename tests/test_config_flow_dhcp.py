"""DHCP discovery flow tests."""

from __future__ import annotations

from unittest.mock import ANY, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_MAC_ADDRESS, DOMAIN

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
        # Collapse the boot-race retry schedule so a closed port aborts
        # immediately instead of sleeping through the real delays.
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps._PROBE_RETRY_DELAYS",
            (0,),
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


async def test_dhcp_discovery_retries_probe_for_booting_printer(hass):
    """The DHCP lease lands before port 9100 is up on a booting printer --
    the probe must retry instead of aborting on the first refusal."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps._can_connect",
            side_effect=[False, False, True],
        ) as mock_connect,
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps._PROBE_RETRY_DELAYS",
            (0, 0, 0),
        ),
        patch(
            "custom_components.escpos_printer._config_flow.discovery_steps.query_printer_id",
            return_value={"manufacturer": "EPSON", "model": "TM-T20II"},
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_DHCP}, data=DISCOVERY
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "network"
    assert mock_connect.call_count == 3


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


async def test_dhcp_discovery_edited_port_requeries_instead_of_reusing_detection(hass):
    """Editing only the port (same discovery host) must not carry over the
    discovery-time GS I result -- DHCP always probes DEFAULT_PORT, so a
    different port may be a different service on the same address."""
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )
    assert result["step_id"] == "network"

    edited_port = 9101
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
            result["flow_id"], {"host": "192.168.10.157", "port": edited_port}
        )
        # Complete the codepage step with defaults to create the entry.
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["detected_manufacturer"] == "OTHER"
    assert result["data"]["detected_model"] == "RP820"
    mock_query.assert_called_once_with("192.168.10.157", edited_port, ANY)


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
    # Entry title is model-based when a model was detected.
    assert result["title"] == "TM-T20II (192.168.10.157:9100)"


async def test_dhcp_discovery_persists_mac_address(hass):
    """A discovery-created entry (unedited host/port) carries the DHCP MAC."""
    with patch(
        "custom_components.escpos_printer._config_flow.network_steps._can_connect",
        return_value=True,
    ):
        result = await _start_dhcp_flow(
            hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.10.157", "port": 9100}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_MAC_ADDRESS] == format_mac(DISCOVERY.macaddress)
    assert result["data"][CONF_MAC_ADDRESS] == "50:57:9c:62:8e:52"


async def test_dhcp_discovery_edited_host_does_not_persist_mac(hass):
    """Editing the suggested host must not attribute the discovery MAC to it."""
    result = await _start_dhcp_flow(
        hass, query_result={"manufacturer": "EPSON", "model": "TM-T20II"}
    )

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.10.200", "port": 9100}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert CONF_MAC_ADDRESS not in result["data"]


async def test_dhcp_discovery_known_mac_new_ip_updates_existing_entry(hass):
    """A DHCP lease change (same MAC, new IP) updates the existing entry in place.

    The entry's auto-generated title (matching its old "host:port") follows
    the relocation, and the reload actually fires.
    """
    mac = format_mac(DISCOVERY.macaddress)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="192.168.10.157:9100",
        unique_id="192.168.10.157:9100",
        data={
            "connection_type": "network",
            "host": "192.168.10.157",
            "port": 9100,
            CONF_MAC_ADDRESS: mac,
        },
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.escpos_printer.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await _start_dhcp_flow(
            hass,
            discovery=DhcpServiceInfo(
                ip="192.168.10.200",
                hostname="TM-T20II-628E52",
                macaddress=DISCOVERY.macaddress,
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    mock_setup.assert_called_once()  # reload actually fired

    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.data["host"] == "192.168.10.200"
    assert updated.unique_id == "192.168.10.200:9100"
    assert updated.title == "192.168.10.200:9100"  # auto-generated title follows


async def test_dhcp_discovery_known_mac_new_ip_model_title_follows(hass):
    """A model-based auto title ("TM-T20II (host:port)") counts as
    auto-generated too and follows the relocation."""
    mac = format_mac(DISCOVERY.macaddress)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="TM-T20II (192.168.10.157:9100)",
        unique_id="192.168.10.157:9100",
        data={
            "connection_type": "network",
            "host": "192.168.10.157",
            "port": 9100,
            "detected_manufacturer": "EPSON",
            "detected_model": "TM-T20II",
            CONF_MAC_ADDRESS: mac,
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await _start_dhcp_flow(
            hass,
            discovery=DhcpServiceInfo(
                ip="192.168.10.200",
                hostname="TM-T20II-628E52",
                macaddress=DISCOVERY.macaddress,
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.data["host"] == "192.168.10.200"
    assert updated.title == "TM-T20II (192.168.10.200:9100)"


async def test_dhcp_discovery_known_mac_new_ip_preserves_manual_rename(hass):
    """A relocation must never clobber a user-renamed title."""
    mac = format_mac(DISCOVERY.macaddress)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front Counter Printer",  # manually renamed, not "host:port"
        unique_id="192.168.10.157:9100",
        data={
            "connection_type": "network",
            "host": "192.168.10.157",
            "port": 9100,
            CONF_MAC_ADDRESS: mac,
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await _start_dhcp_flow(
            hass,
            discovery=DhcpServiceInfo(
                ip="192.168.10.200",
                hostname="TM-T20II-628E52",
                macaddress=DISCOVERY.macaddress,
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.title == "Front Counter Printer"  # untouched


async def test_dhcp_discovery_known_mac_new_ip_keeps_entry_port(hass):
    """Relocation uses the entry's STORED port, not DEFAULT_PORT."""
    mac = format_mac(DISCOVERY.macaddress)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9101",
        data={
            "connection_type": "network",
            "host": "192.168.10.157",
            "port": 9101,
            CONF_MAC_ADDRESS: mac,
        },
    )
    entry.add_to_hass(hass)

    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result = await _start_dhcp_flow(
            hass,
            discovery=DhcpServiceInfo(
                ip="192.168.10.200",
                hostname="TM-T20II-628E52",
                macaddress=DISCOVERY.macaddress,
            ),
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.unique_id == "192.168.10.200:9101"


async def test_dhcp_discovery_known_mac_new_ip_collision_skips_update(hass):
    """If the new ip:port is already owned by a different entry, the MAC-tracked
    entry is left untouched and normal dedupe applies."""
    mac = format_mac(DISCOVERY.macaddress)
    tracked = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9100",
        data={
            "connection_type": "network",
            "host": "192.168.10.157",
            "port": 9100,
            CONF_MAC_ADDRESS: mac,
        },
    )
    tracked.add_to_hass(hass)
    other = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.200:9100",
        data={"connection_type": "network", "host": "192.168.10.200", "port": 9100},
    )
    other.add_to_hass(hass)

    result = await _start_dhcp_flow(
        hass,
        discovery=DhcpServiceInfo(
            ip="192.168.10.200",
            hostname="TM-T20II-628E52",
            macaddress=DISCOVERY.macaddress,
        ),
    )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    tracked_updated = hass.config_entries.async_get_entry(tracked.entry_id)
    assert tracked_updated.data["host"] == "192.168.10.157"
    assert tracked_updated.unique_id == "192.168.10.157:9100"  # untouched
    assert len(hass.config_entries.async_entries(DOMAIN)) == 2


async def test_dhcp_discovery_known_mac_same_ip_normal_abort(hass):
    """A known MAC at the same IP falls through to the ordinary
    already-configured unique_id dedupe (no update, no reload)."""
    mac = format_mac(DISCOVERY.macaddress)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9100",
        data={
            "connection_type": "network",
            "host": "192.168.10.157",
            "port": 9100,
            CONF_MAC_ADDRESS: mac,
        },
    )
    entry.add_to_hass(hass)

    result = await _start_dhcp_flow(hass)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_dhcp_discovery_matched_entry_without_mac_adopts_it(hass):
    """An already-configured entry at the discovered IP that has no stored MAC
    yet adopts it -- pre-existing and manually-created entries gain lease
    tracking the first time discovery sees them."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="192.168.10.157:9100",
        data={"connection_type": "network", "host": "192.168.10.157", "port": 9100},
    )
    entry.add_to_hass(hass)

    result = await _start_dhcp_flow(hass)

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    updated = hass.config_entries.async_get_entry(entry.entry_id)
    assert updated is not None
    assert updated.data[CONF_MAC_ADDRESS] == format_mac(DISCOVERY.macaddress)


async def test_dhcp_discovery_rongta_clone_overrides_epson_emulation(hass):
    """A Rongta board answering GS I as "EPSON TM-T88III" (clone firmware
    impersonating its emulation target) must not hijack the discovered
    identity -- the brand hostname is authoritative."""
    result = await _start_dhcp_flow(
        hass,
        query_result={"manufacturer": "EPSON", "model": "TM-T88III"},
        discovery=DISCOVERY_RONGTA,
    )
    assert result["step_id"] == "network"
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {"name": "RP820 (192.168.10.158)"}

    # The overridden identity ("RP820") resolves directly to the custom
    # RP820 profile -- not to the emulated TM-T88III.
    defaults = result["data_schema"]({"host": "192.168.10.158"})
    assert defaults["profile"] == "RP820"

    with patch(
        "custom_components.escpos_printer._config_flow.network_steps._can_connect",
        return_value=True,
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"host": "192.168.10.158", "port": 9100}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["detected_manufacturer"] == "Rongta"
    assert result["data"]["detected_model"] == "RP820"


async def test_dhcp_discovery_rongta_branded_gs_i_reply_kept(hass):
    """A rongta_* hostname whose GS I reply IS Rongta-branded keeps that
    identity untouched -- the override only fires on a brand mismatch."""
    await _start_dhcp_flow(
        hass,
        query_result={"manufacturer": "Rongta", "model": "RP850P"},
        discovery=DISCOVERY_RONGTA,
    )
    flow = hass.config_entries.flow.async_progress()[0]
    assert flow["context"]["title_placeholders"] == {"name": "RP850P (192.168.10.158)"}


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
