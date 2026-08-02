"""Tests for USB no-serial unique-ID dedup and the reconfigure flow."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import (
    CONF_BAUDRATE,
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_ALIGN,
    CONF_DEFAULT_CUT,
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
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


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

    with patch(
        "custom_components.escpos_printer._config_flow.network_steps._can_connect",
        return_value=True,
    ) as mock_connect:
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
    data = {CONF_VENDOR_ID: 0x04B8, CONF_PRODUCT_ID: 0x0202, "timeout": 4.0, "profile": ""}
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
