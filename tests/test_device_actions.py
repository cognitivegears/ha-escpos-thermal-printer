"""Tests for device_action/actions.py."""

from unittest.mock import patch

from homeassistant.const import CONF_DEVICE_ID, CONF_HOST, CONF_PORT, CONF_TYPE
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.device_action import (
    async_call_action_from_config,
)


async def _setup_and_get_device_id(hass) -> tuple[MockConfigEntry, str]:  # type: ignore[no-untyped-def]
    """Set up an entry, return (entry, device_id) for action targeting."""
    from homeassistant.helpers import device_registry as dr

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

    # Locate the device registered for this entry
    device_registry = dr.async_get(hass)
    device = next(
        (d for d in device_registry.devices.values() if entry.entry_id in d.config_entries),
        None,
    )
    assert device is not None, "Expected a device entry for the printer"
    return entry, device.id


async def test_call_action_print_text(hass):  # type: ignore[no-untyped-def]
    """print_text action should reach the adapter's print_text method."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_text", wraps=adapter.print_text) as spy:
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: device_id, CONF_TYPE: "print_text", "text": "Hello"},
            {},
            None,
        )
    spy.assert_called_once()
    assert spy.call_args.kwargs["text"] == "Hello"


async def test_call_action_print_text_utf8(hass):  # type: ignore[no-untyped-def]
    """print_text_utf8 should transcode and then call adapter.print_text."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_text", wraps=adapter.print_text) as spy:
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: device_id, CONF_TYPE: "print_text_utf8", "text": "Café"},
            {},
            None,
        )
    spy.assert_called_once()
    # encoding is forced None so the printer uses its configured codepage
    assert spy.call_args.kwargs["encoding"] is None


async def test_call_action_print_qr(hass):  # type: ignore[no-untyped-def]
    """print_qr action should reach adapter.print_qr."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_qr", wraps=adapter.print_qr) as spy:
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: device_id, CONF_TYPE: "print_qr", "data": "https://example.com"},
            {},
            None,
        )
    spy.assert_called_once()
    assert spy.call_args.kwargs["data"] == "https://example.com"


async def test_call_action_print_barcode(hass):  # type: ignore[no-untyped-def]
    """print_barcode action should reach adapter.print_barcode."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_barcode", wraps=adapter.print_barcode) as spy:
        await async_call_action_from_config(
            hass,
            {
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: "print_barcode",
                "code": "1234567890128",
                "bc": "EAN13",
            },
            {},
            None,
        )
    spy.assert_called_once()
    assert spy.call_args.kwargs["code"] == "1234567890128"
    assert spy.call_args.kwargs["bc"] == "EAN13"


async def test_call_action_feed(hass):  # type: ignore[no-untyped-def]
    """feed action should reach adapter.feed."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "feed", wraps=adapter.feed) as spy:
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: device_id, CONF_TYPE: "feed", "lines": 3},
            {},
            None,
        )
    spy.assert_called_once_with(hass, lines=3)


async def test_call_action_cut(hass):  # type: ignore[no-untyped-def]
    """cut action should reach adapter.cut."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "cut", wraps=adapter.cut) as spy:
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: device_id, CONF_TYPE: "cut", "mode": "partial"},
            {},
            None,
        )
    spy.assert_called_once_with(hass, mode="partial")


async def test_call_action_beep(hass):  # type: ignore[no-untyped-def]
    """beep action should reach adapter.beep with default times/duration."""
    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "beep", wraps=adapter.beep) as spy:
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: device_id, CONF_TYPE: "beep"},
            {},
            None,
        )
    spy.assert_called_once()
    assert spy.call_args.kwargs["times"] == 2
    assert spy.call_args.kwargs["duration"] == 4


async def test_call_action_unknown_device_raises(hass):  # type: ignore[no-untyped-def]
    """An unknown device_id must raise ValueError."""
    with pytest.raises(ValueError, match="not found"):
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: "nonexistent_device", CONF_TYPE: "feed", "lines": 1},
            {},
            None,
        )


async def test_call_action_device_without_domain_identifier_raises(hass):  # type: ignore[no-untyped-def]
    """A device that exists but has no DOMAIN identifier must raise."""
    from homeassistant.helpers import device_registry as dr

    # Create a foreign config entry + device that ISN'T ours
    foreign_entry = MockConfigEntry(domain="other_integration", data={})
    foreign_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    foreign_device = device_registry.async_get_or_create(
        config_entry_id=foreign_entry.entry_id,
        identifiers={("other_integration", "some_id")},
    )

    with pytest.raises(ValueError, match="not found"):
        await async_call_action_from_config(
            hass,
            {CONF_DEVICE_ID: foreign_device.id, CONF_TYPE: "feed", "lines": 1},
            {},
            None,
        )


async def test_call_action_print_image_local(hass, tmp_path):  # type: ignore[no-untyped-def]
    """print_image action should reach adapter.print_image."""
    from PIL import Image as PILImage

    entry, device_id = await _setup_and_get_device_id(hass)
    adapter = entry.runtime_data.adapter

    # Create a tiny local image to print
    img_path = tmp_path / "test.png"
    PILImage.new("RGB", (32, 32), "white").save(img_path)

    with patch.object(adapter, "print_image", wraps=adapter.print_image) as spy:
        await async_call_action_from_config(
            hass,
            {
                CONF_DEVICE_ID: device_id,
                CONF_TYPE: "print_image",
                "image": str(img_path),
            },
            {},
            None,
        )
    spy.assert_called_once()
    assert spy.call_args.kwargs["image"] == str(img_path)
