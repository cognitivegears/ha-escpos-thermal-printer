"""Tests for the per-entry paper width override."""

from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer import _shared_print_config
from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONF_TIMEOUT,
    CONF_WIDTH_PIXELS,
    CONNECTION_TYPE_NETWORK,
    DOMAIN,
)
from custom_components.escpos_printer.printer import create_printer_adapter
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig


def test_width_override_beats_profile() -> None:
    # TM-T20II declares 576px; use a distinct override value so this test
    # actually proves the override wins rather than coincidentally matching.
    config = NetworkPrinterConfig(host="127.0.0.1", profile="TM-T20II", width_pixels=384)
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 384


def test_width_override_without_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile=None, width_pixels=384)
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 384


def test_no_override_uses_profile() -> None:
    config = NetworkPrinterConfig(host="127.0.0.1", profile="TM-T20II")
    adapter = create_printer_adapter(config)
    assert adapter.get_profile_pixel_width() == 576  # TM-T20II declares 576px


async def test_options_flow_clears_width_override(hass) -> None:  # type: ignore[no-untyped-def]
    """Clearing width_pixels in the options form must clear the override.

    Regression test: without an explicit ``None`` stored in options, the
    resolution rule ``opt.get(K, data.get(K))`` fell back to the setup-time
    value in entry.data, making a width override impossible to remove once
    set.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_TIMEOUT: 4.0,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
            CONF_WIDTH_PIXELS: 576,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    with patch("custom_components.escpos_printer.async_setup_entry", return_value=True):
        result2 = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_TIMEOUT: 4.0,
                # CONF_WIDTH_PIXELS deliberately omitted -- simulates the
                # user clearing the field in the UI.
            },
        )
        await hass.async_block_till_done()

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_WIDTH_PIXELS] is None
    assert _shared_print_config(entry)["width_pixels"] is None
