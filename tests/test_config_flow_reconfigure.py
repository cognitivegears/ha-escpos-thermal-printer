"""Tests for USB no-serial unique-ID dedup and the reconfigure flow."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry
import voluptuous as vol

from custom_components.escpos_printer.const import (
    CONF_BAUDRATE,
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
    CONF_DETECTED_MANUFACTURER,
    CONF_DETECTED_MODEL,
    CONF_IN_EP,
    CONF_LINE_WIDTH,
    CONF_OUT_EP,
    CONF_PRODUCT_ID,
    CONF_RFCOMM_CHANNEL,
    CONF_SERIAL_PORT,
    CONF_TIMEOUT,
    CONF_VENDOR_ID,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
    DEFAULT_LINE_WIDTH,
    DOMAIN,
)


async def _run_usb_select_flow(hass):  # type: ignore[no-untyped-def]
    """Drive the user flow up to the usb_select submission and return the result."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
    )
    assert result2["step_id"] == "usb_select"
    return await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {"usb_device": "04B8:0202#0", "timeout": 4.0, "profile": ""},
    )


async def test_usb_no_serial_fallback_unique_id_dedup(hass):  # type: ignore[no-untyped-def]
    """A serial-less USB printer gets a usb:vid:pid unique ID and can't be added twice."""
    no_serial_device = {
        "vendor_id": 0x04B8,
        "product_id": 0x0202,
        "manufacturer": "Epson",
        "product": "TM-T88V",
        "serial_number": None,
        "label": "Epson TM-T88V (04B8:0202)",
    }

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[no_serial_device],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(True, None, None),
        ),
    ):
        result = await _run_usb_select_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "codepage"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: str(DEFAULT_LINE_WIDTH),
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )
        assert result2["type"] == "create_entry"

        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "usb:04b8:0202"

        # Second attempt at the same serial-less device must dedupe.
        result3 = await _run_usb_select_flow(hass)
        assert result3["type"] == "abort"
        assert result3["reason"] == "already_configured"
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reconfigure_network_happy_path(hass):  # type: ignore[no-untyped-def]
    """Reconfiguring a network printer's host updates the same entry in place."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_network"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 9100},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.entry_id == entry_id  # same entry -- entities/automations survive
    assert updated.data[CONF_HOST] == "5.6.7.8"
    assert updated.unique_id == "5.6.7.8:9100"
    assert updated.title == "5.6.7.8:9100"  # auto-generated title follows the new address
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_reconfigure_network_preserves_manual_rename(hass):  # type: ignore[no-untyped-def]
    """A user-renamed title must survive a reconfigure to a new address."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Front Counter Printer",  # manually renamed, not "host:port"
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 9100},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_HOST] == "5.6.7.8"
    assert updated.title == "Front Counter Printer"  # untouched


async def test_reconfigure_network_detected_fields_replace_on_requery(hass):  # type: ignore[no-untyped-def]
    """A fresh GS I result on reconfigure REPLACES prior detected state.

    Reconfigure may point the entry at a different printer, so a detected
    manufacturer/model must overwrite when present and be removed (not just
    left stale) when the fresh query comes back empty.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value={"manufacturer": "EPSON", "model": "TM-T20II"},
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 9100},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_DETECTED_MANUFACTURER] == "EPSON"
    assert updated.data[CONF_DETECTED_MODEL] == "TM-T20II"

    # Reconfigure again onto a printer that doesn't answer GS I -- the
    # previous printer's detected fields must be removed, not kept stale.
    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result3 = await entry.start_reconfigure_flow(hass)
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {CONF_HOST: "9.9.9.9", CONF_PORT: 9100},
        )
        await hass.async_block_till_done()

    assert result4["type"] == "abort"
    assert result4["reason"] == "reconfigure_successful"

    updated2 = hass.config_entries.async_get_entry(entry_id)
    assert updated2 is not None
    assert CONF_DETECTED_MANUFACTURER not in updated2.data
    assert CONF_DETECTED_MODEL not in updated2.data


async def test_reconfigure_network_cannot_connect(hass):  # type: ignore[no-untyped-def]
    """A failed connection probe re-renders the form with cannot_connect and leaves the entry alone."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=False,
        ),
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "5.6.7.8", CONF_PORT: 9100},
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "reconfigure_network"
    assert result2["errors"]["base"] == "cannot_connect"
    assert entry.data[CONF_HOST] == "1.2.3.4"  # untouched


async def test_reconfigure_bluetooth_unique_id_mismatch_aborts(hass):  # type: ignore[no-untyped-def]
    """Reconfiguring Bluetooth to a *different* MAC aborts instead of hijacking the entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.escpos_printer._config_flow.bluetooth_steps._can_connect_bluetooth",
        return_value=(True, None, None),
    ) as mock_connect:
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_bluetooth"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BT_MAC: "11:22:33:44:55:66", CONF_RFCOMM_CHANNEL: 1},
        )

    assert result2["type"] == "abort"
    assert result2["reason"] == "unique_id_mismatch"
    mock_connect.assert_not_called()
    # Entry is untouched -- the mismatch guard fires before any update.
    assert entry.data[CONF_BT_MAC] == "AA:BB:CC:DD:EE:FF"


async def test_reconfigure_usb_backfills_unique_id_when_none(hass):  # type: ignore[no-untyped-def]
    """A pre-existing serial-less USB entry (unique_id=None) can be reconfigured.

    B1: ``_abort_if_unique_id_mismatch`` never matches when the entry's
    stored unique_id is None, which used to block reconfigure forever.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id=None,
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    discovered = {
        "vendor_id": 0x04B8,
        "product_id": 0x0202,
        "manufacturer": "Epson",
        "product": "TM-T88V",
        "serial_number": None,
        "label": "Epson TM-T88V (04B8:0202)",
        "_choice_key": "04B8:0202#0",
    }

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[discovered],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(True, None, None),
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_usb"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"usb_device": "04B8:0202#0", "timeout": 4.0},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.unique_id == "usb:04b8:0202"


async def test_reconfigure_usb_manual_keeps_serial_suffixed_unique_id(hass):  # type: ignore[no-untyped-def]
    """B4: reconfiguring via the manual VID:PID fallback keeps a
    serial-suffixed unique_id instead of dead-ending on a mismatch.

    reconfigure_usb_manual never asks for a serial number, so it always
    recomputes a bare "usb:vid:pid" id. That must not mismatch against an
    entry whose original unique_id was serial-suffixed -- the vid:pid base
    still matches, so the entry's existing (serial-suffixed) unique_id is
    kept.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202:SN12345",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[],  # nothing discovered -> forces the manual fallback
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(True, None, None),
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_usb"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"usb_device": "__manual__"}
        )
        assert result2["step_id"] == "reconfigure_usb_manual"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_VENDOR_ID: "0x04B8", CONF_PRODUCT_ID: "0x0202", "timeout": 4.0},
        )
        await hass.async_block_till_done()

    assert result3["type"] == "abort"
    assert result3["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.unique_id == "usb:04b8:0202:SN12345"  # kept, not dropped


async def test_reconfigure_usb_manual_different_vid_pid_still_aborts(hass):  # type: ignore[no-untyped-def]
    """A genuinely different vid:pid base must still trip the mismatch guard."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202:SN12345",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb"
        ) as mock_can_connect,
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"usb_device": "__manual__"}
        )
        assert result2["step_id"] == "reconfigure_usb_manual"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_VENDOR_ID: "0x0483", CONF_PRODUCT_ID: "0x5720", "timeout": 4.0},
        )

    assert result3["type"] == "abort"
    assert result3["reason"] == "unique_id_mismatch"
    mock_can_connect.assert_not_called()  # mismatch guard fires before any probe
    assert entry.unique_id == "usb:04b8:0202:SN12345"  # untouched


async def test_reconfigure_usb_manual_seeds_stored_timeout(hass):  # type: ignore[no-untyped-def]
    """B5: opening the manual USB reconfigure form suggests the entry's
    stored timeout instead of silently defaulting to DEFAULT_TIMEOUT on
    the next submit (unlike network/serial/bluetooth reconfigure, this
    form didn't call ``add_suggested_values_to_schema``).
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 12.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=[],
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"usb_device": "__manual__"}
        )

    assert result2["step_id"] == "reconfigure_usb_manual"
    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result2["data_schema"].schema
        if isinstance(key, vol.Marker) and key.description
    }
    assert suggested[CONF_TIMEOUT] == 12.0


async def test_reconfigure_usb_seeds_stored_timeout(hass):  # type: ignore[no-untyped-def]
    """B5: same guard as above, for the discovery-backed reconfigure_usb form."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 9.5,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202",
    )
    entry.add_to_hass(hass)

    discovered = {
        "vendor_id": 0x04B8,
        "product_id": 0x0202,
        "manufacturer": "Epson",
        "product": "TM-T88V",
        "serial_number": None,
        "label": "Epson TM-T88V (04B8:0202)",
        "_choice_key": "04B8:0202#0",
    }
    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=[discovered],
    ):
        result = await entry.start_reconfigure_flow(hass)

    assert result["step_id"] == "reconfigure_usb"
    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if isinstance(key, vol.Marker) and key.description
    }
    assert suggested[CONF_TIMEOUT] == 9.5


async def test_reconfigure_usb_preselects_configured_device(hass):  # type: ignore[no-untyped-def]
    """The reconfigure_usb dropdown must preselect the entry's configured
    device, not just default to the first discovered one.

    Regression test: ``reconfigure_entry.data`` has no ``usb_device`` key
    (that's a UI-only choice-dict key, never stored), so
    ``add_suggested_values_to_schema`` had nothing to suggest for that
    field and it silently fell back to ``next(iter(device_choices))`` --
    whichever device ``usb.core.find()`` happened to enumerate first.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0E28",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0E28,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0e28",
    )
    entry.add_to_hass(hass)

    # Two devices discovered; the configured one (04B8:0E28) is NOT first.
    discovered = [
        {
            "vendor_id": 0x04B8,
            "product_id": 0x0202,
            "manufacturer": "Epson",
            "product": "TM-T88V",
            "serial_number": None,
            "label": "Epson TM-T88V (04B8:0202)",
        },
        {
            "vendor_id": 0x04B8,
            "product_id": 0x0E28,
            "manufacturer": "Epson",
            "product": "TM-T20II",
            "serial_number": None,
            "label": "Epson TM-T20II (04B8:0E28)",
        },
    ]
    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=discovered,
    ):
        result = await entry.start_reconfigure_flow(hass)

    assert result["step_id"] == "reconfigure_usb"
    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if isinstance(key, vol.Marker) and key.description
    }
    assert suggested["usb_device"] == "04B8:0E28#0"


async def test_reconfigure_usb_falls_back_when_configured_device_missing(hass):  # type: ignore[no-untyped-def]
    """If the configured device isn't among the discovered ones (e.g.
    unplugged), fall back to the first discovered device -- today's
    behaviour -- rather than erroring.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:FFFF",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0xFFFF,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:ffff",
    )
    entry.add_to_hass(hass)

    discovered = [
        {
            "vendor_id": 0x04B8,
            "product_id": 0x0202,
            "manufacturer": "Epson",
            "product": "TM-T88V",
            "serial_number": None,
            "label": "Epson TM-T88V (04B8:0202)",
        },
    ]
    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=discovered,
    ):
        result = await entry.start_reconfigure_flow(hass)

    assert result["step_id"] == "reconfigure_usb"
    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if isinstance(key, vol.Marker) and key.description
    }
    assert suggested["usb_device"] == "04B8:0202#0"


async def test_reconfigure_network_case_insensitive_collision_aborts(hass):  # type: ignore[no-untyped-def]
    """Reconfiguring to a host that only differs in case from another entry aborts.

    B2: the raw ``_async_abort_entries_match`` compare is case-sensitive
    but the unique_id is lower-cased, so "Printer.local" and
    "printer.local" used to pass the guard and collide on unique_id.
    """
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Printer.local:9100",
        data={
            CONF_HOST: "Printer.local",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="printer.local:9100",
    )
    existing.add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.network_steps._can_connect",
            return_value=True,
        ) as mock_connect,
        patch(
            "custom_components.escpos_printer._config_flow.network_steps.query_printer_id",
            return_value=None,
        ),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure_network"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_HOST: "printer.local", CONF_PORT: 9100},
        )

    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"
    mock_connect.assert_not_called()

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_HOST] == "1.2.3.4"  # untouched


async def test_reconfigure_serial_case_insensitive_collision_aborts(hass):  # type: ignore[no-untyped-def]
    """Same case-collision guard as network, for the serial port path."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        title="Serial /dev/TTYUSB0",
        data={
            CONF_SERIAL_PORT: "/dev/TTYUSB0",
            CONF_BAUDRATE: 9600,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        },
        unique_id="serial:/dev/ttyusb0",
    )
    existing.add_to_hass(hass)

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serial /dev/ttyUSB1",
        data={
            CONF_SERIAL_PORT: "/dev/ttyUSB1",
            CONF_BAUDRATE: 9600,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        },
        unique_id="serial:/dev/ttyusb1",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with patch(
        "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
        return_value=(True, None, None),
    ) as mock_connect:
        result = await entry.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure_serial"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SERIAL_PORT: "/dev/ttyUSB0", CONF_BAUDRATE: "9600"},
        )

    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"
    mock_connect.assert_not_called()

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_SERIAL_PORT] == "/dev/ttyUSB1"  # untouched


async def _run_usb_manual_flow(hass, **overrides):  # type: ignore[no-untyped-def]
    """Drive the user flow through usb_manual (no printers discovered)."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB}
    )
    assert result2["step_id"] == "usb_select"
    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"], {"usb_device": "__manual__"}
    )
    assert result3["step_id"] == "usb_manual"
    data = {CONF_VENDOR_ID: "0x04B8", CONF_PRODUCT_ID: "0x0202", "timeout": 4.0, "profile": ""}
    data.update(overrides)
    return await hass.config_entries.flow.async_configure(result3["flow_id"], data)


async def test_usb_manual_default_endpoint_duplicate_aborts(hass):  # type: ignore[no-untyped-def]
    """B3: manual USB entry now gets a unique ID; a default-endpoint dup aborts."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(True, None, None),
        ),
    ):
        result3 = await _run_usb_manual_flow(hass)
        assert result3["step_id"] == "codepage"
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: str(DEFAULT_LINE_WIDTH),
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )
        assert result4["type"] == "create_entry"

        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 1
        assert entries[0].unique_id == "usb:04b8:0202"

        # A second manual entry at the default endpoints is a real duplicate.
        result_dup = await _run_usb_manual_flow(hass)
        assert result_dup["type"] == "abort"
        assert result_dup["reason"] == "already_configured"
        assert len(hass.config_entries.async_entries(DOMAIN)) == 1


async def test_usb_manual_custom_endpoint_coexists_with_default(hass):  # type: ignore[no-untyped-def]
    """B3: custom in_ep/out_ep legitimately distinguishes a second entry."""
    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(True, None, None),
        ),
    ):
        result3 = await _run_usb_manual_flow(hass)
        result4 = await hass.config_entries.flow.async_configure(
            result3["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: str(DEFAULT_LINE_WIDTH),
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )
        assert result4["type"] == "create_entry"

        result3b = await _run_usb_manual_flow(hass, in_ep=0x83, out_ep=0x02)
        assert result3b["step_id"] == "codepage"
        result4b = await hass.config_entries.flow.async_configure(
            result3b["flow_id"],
            {
                CONF_CODEPAGE: "",
                CONF_LINE_WIDTH: str(DEFAULT_LINE_WIDTH),
                CONF_DEFAULT_ALIGN: "left",
                CONF_DEFAULT_CUT: "none",
            },
        )
        assert result4b["type"] == "create_entry"

        entries = hass.config_entries.async_entries(DOMAIN)
        assert len(entries) == 2
        unique_ids = {e.unique_id for e in entries}
        assert unique_ids == {"usb:04b8:0202", "usb:04b8:0202:83:02"}


async def test_reconfigure_usb_legacy_collision_with_other_entry_aborts(hass):  # type: ignore[no-untyped-def]
    """A legacy (unique_id=None) USB entry reconfigured onto a device already
    owned by a *different* entry must abort, not adopt a duplicate unique_id.
    """
    owner = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202",
    )
    owner.add_to_hass(hass)

    legacy = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202 (legacy)",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id=None,
    )
    legacy.add_to_hass(hass)

    discovered = {
        "vendor_id": 0x04B8,
        "product_id": 0x0202,
        "manufacturer": "Epson",
        "product": "TM-T88V",
        "serial_number": None,
        "label": "Epson TM-T88V (04B8:0202)",
        "_choice_key": "04B8:0202#0",
    }

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[discovered],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb"
        ) as mock_can_connect,
    ):
        result = await legacy.start_reconfigure_flow(hass)
        assert result["step_id"] == "reconfigure_usb"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"usb_device": "04B8:0202#0", "timeout": 4.0},
        )

    assert result2["type"] == "abort"
    assert result2["reason"] == "already_configured"
    mock_can_connect.assert_not_called()  # collision guard fires before any probe
    assert legacy.unique_id is None  # legacy entry left untouched


async def test_reconfigure_usb_uses_stored_endpoints_for_probe(hass):  # type: ignore[no-untyped-def]
    """A manual entry with custom in_ep/out_ep is re-probed under those same endpoints."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_IN_EP: 0x83,
            CONF_OUT_EP: 0x02,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202:83:02",
    )
    entry.add_to_hass(hass)

    discovered = {
        "vendor_id": 0x04B8,
        "product_id": 0x0202,
        "manufacturer": "Epson",
        "product": "TM-T88V",
        "serial_number": None,
        "label": "Epson TM-T88V (04B8:0202)",
        "_choice_key": "04B8:0202#0",
    }

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[discovered],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(True, None, None),
        ) as mock_can_connect,
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"usb_device": "04B8:0202#0", "timeout": 4.0},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    mock_can_connect.assert_called_once_with(0x04B8, 0x0202, 4.0, 0x83, 0x02)


async def test_reconfigure_usb_invalid_device_selection_shows_error(hass):  # type: ignore[no-untyped-def]
    """Selecting a choice key that no longer matches a discovered printer errors."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202",
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=[],
    ):
        result = await entry.start_reconfigure_flow(hass)
        # A stale choice key can't reach here through vol.In(device_choices)
        # in the real UI (the dropdown only ever offers current choices) --
        # call the step directly, bypassing schema validation, to exercise
        # the handler's own "not found" guard.
        flow = hass.config_entries.flow._progress[result["flow_id"]]
        result2 = await flow.async_step_reconfigure_usb(
            {"usb_device": "no_longer_present#0", "timeout": 4.0}
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "reconfigure_usb"
    assert result2["errors"]["base"] == "invalid_usb_device"


async def test_reconfigure_usb_manual_sentinel_routes_to_manual_step(hass):  # type: ignore[no-untyped-def]
    """Picking the manual-entry sentinel routes to reconfigure_usb_manual."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202",
    )
    entry.add_to_hass(hass)

    discovered = {
        "vendor_id": 0x04B8,
        "product_id": 0x0202,
        "manufacturer": "Epson",
        "product": "TM-T88V",
        "serial_number": None,
        "label": "Epson TM-T88V (04B8:0202)",
        "_choice_key": "04B8:0202#0",
    }
    with patch(
        "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
        return_value=[discovered],
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"usb_device": "__manual__"}
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "reconfigure_usb_manual"


async def test_finalize_usb_reconfigure_probe_failure_shows_error(hass):  # type: ignore[no-untyped-def]
    """A failed connect probe re-renders the manual reconfigure form with an error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="USB Printer 04B8:0202",
        data={
            CONF_VENDOR_ID: 0x04B8,
            CONF_PRODUCT_ID: 0x0202,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_USB,
        },
        unique_id="usb:04b8:0202",
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._discover_usb_printers",
            return_value=[],
        ),
        patch(
            "custom_components.escpos_printer._config_flow.usb_steps._can_connect_usb",
            return_value=(False, "device_not_found", 19),
        ),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"usb_device": "__manual__"}
        )
        assert result2["step_id"] == "reconfigure_usb_manual"

        result3 = await hass.config_entries.flow.async_configure(
            result2["flow_id"],
            {CONF_VENDOR_ID: "0x04B8", CONF_PRODUCT_ID: "0x0202", "timeout": 4.0},
        )

    assert result3["type"] == "form"
    assert result3["step_id"] == "reconfigure_usb_manual"
    assert result3["errors"]["base"] == "usb_device_not_found"
    assert entry.unique_id == "usb:04b8:0202"  # untouched


async def test_reconfigure_serial_happy_path(hass):  # type: ignore[no-untyped-def]
    """Reconfiguring a serial printer's port updates the same entry and its auto title."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serial /dev/ttyUSB0",
        data={
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
            CONF_BAUDRATE: 9600,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        },
        unique_id="serial:/dev/ttyusb0",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
            return_value=(True, None, None),
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_serial"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SERIAL_PORT: "/dev/ttyUSB1", CONF_BAUDRATE: "19200"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_SERIAL_PORT] == "/dev/ttyUSB1"
    assert updated.data[CONF_BAUDRATE] == 19200
    assert updated.unique_id == "serial:/dev/ttyusb1"
    assert updated.title == "Serial /dev/ttyUSB1"  # auto-generated title follows the new port


async def test_reconfigure_serial_suggests_stored_baudrate_as_string(hass):  # type: ignore[no-untyped-def]
    """CONF_BAUDRATE is stored as int, but the dropdown's choices are string
    keys -- the suggested value must be normalised to str or the field
    fails to preselect and an untouched submit silently falls back to the
    schema default (9600) instead of the entry's real (non-default) rate.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serial /dev/ttyUSB0",
        data={
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
            CONF_BAUDRATE: 19200,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        },
        unique_id="serial:/dev/ttyusb0",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure_serial"
    suggested = {
        key.schema: key.description["suggested_value"]
        for key in result["data_schema"].schema
        if isinstance(key, vol.Marker) and key.description
    }
    assert suggested[CONF_BAUDRATE] == "19200"

    with (
        patch(
            "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
            return_value=(True, None, None),
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SERIAL_PORT: "/dev/ttyUSB0", CONF_BAUDRATE: suggested[CONF_BAUDRATE]},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"
    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_BAUDRATE] == 19200  # preserved, not reset to 9600


async def test_reconfigure_serial_preserves_manual_rename(hass):  # type: ignore[no-untyped-def]
    """A user-renamed title must survive a reconfigure to a new port."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Kitchen Receipt Printer",  # manually renamed, not "Serial <port>"
        data={
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
            CONF_BAUDRATE: 9600,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        },
        unique_id="serial:/dev/ttyusb0",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.serial_steps._can_connect_serial",
            return_value=(True, None, None),
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_SERIAL_PORT: "/dev/ttyUSB1", CONF_BAUDRATE: "9600"},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_SERIAL_PORT] == "/dev/ttyUSB1"
    assert updated.title == "Kitchen Receipt Printer"  # untouched


async def test_reconfigure_serial_invalid_baudrate_reorders_cleanly(hass):  # type: ignore[no-untyped-def]
    """A non-numeric baudrate must hit invalid_baudrate, not raise out of int()."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Serial /dev/ttyUSB0",
        data={
            CONF_SERIAL_PORT: "/dev/ttyUSB0",
            CONF_BAUDRATE: 9600,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_SERIAL,
        },
        unique_id="serial:/dev/ttyusb0",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    # A non-numeric baudrate can't reach here through vol.In(_BAUDRATE_CHOICES)
    # in the real UI -- call the step directly, bypassing schema validation,
    # to exercise the handler's own reordered parse-then-check guard.
    flow = hass.config_entries.flow._progress[result["flow_id"]]
    result2 = await flow.async_step_reconfigure_serial(
        {CONF_SERIAL_PORT: "/dev/ttyUSB0", CONF_BAUDRATE: "not-a-number"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "reconfigure_serial"
    assert result2["errors"]["base"] == "invalid_baudrate"
    assert entry.data[CONF_BAUDRATE] == 9600  # untouched


async def test_reconfigure_bluetooth_happy_path(hass):  # type: ignore[no-untyped-def]
    """Reconfiguring a Bluetooth printer's channel updates the same entry in place."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )
    entry.add_to_hass(hass)
    entry_id = entry.entry_id

    with (
        patch(
            "custom_components.escpos_printer._config_flow.bluetooth_steps._can_connect_bluetooth",
            return_value=(True, None, None),
        ),
        patch("custom_components.escpos_printer.async_setup_entry", return_value=True),
    ):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] == "form"
        assert result["step_id"] == "reconfigure_bluetooth"

        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_BT_MAC: "AA:BB:CC:DD:EE:FF", CONF_RFCOMM_CHANNEL: 2},
        )
        await hass.async_block_till_done()

    assert result2["type"] == "abort"
    assert result2["reason"] == "reconfigure_successful"

    updated = hass.config_entries.async_get_entry(entry_id)
    assert updated is not None
    assert updated.data[CONF_RFCOMM_CHANNEL] == 2
    assert updated.unique_id == "bt:aa:bb:cc:dd:ee:ff"


async def test_reconfigure_bluetooth_invalid_mac_shows_error(hass):  # type: ignore[no-untyped-def]
    """An unparsable MAC re-renders the form instead of proceeding."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_BT_MAC: "not-a-mac", CONF_RFCOMM_CHANNEL: 1},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "reconfigure_bluetooth"
    assert result2["errors"]["base"] == "invalid_bt_mac"
    assert entry.data[CONF_BT_MAC] == "AA:BB:CC:DD:EE:FF"  # untouched


async def test_reconfigure_bluetooth_invalid_channel_shows_error(hass):  # type: ignore[no-untyped-def]
    """An out-of-range RFCOMM channel re-renders the form instead of proceeding."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Bluetooth Printer AA:BB:CC:DD:EE:FF",
        data={
            CONF_BT_MAC: "AA:BB:CC:DD:EE:FF",
            CONF_RFCOMM_CHANNEL: 1,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
        },
        unique_id="bt:aa:bb:cc:dd:ee:ff",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reconfigure_flow(hass)
    result2 = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_BT_MAC: "AA:BB:CC:DD:EE:FF", CONF_RFCOMM_CHANNEL: 99},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "reconfigure_bluetooth"
    assert result2["errors"]["base"] == "invalid_rfcomm_channel"
    assert entry.data[CONF_RFCOMM_CHANNEL] == 1  # untouched
