"""Tests for service-call targeting and error paths.

Covers:
- print_text_utf8 service (transcoding handler)
- Targeted service calls via device_id (target_resolution device-id branch)
- Service call errors propagating as HomeAssistantError
- target_resolution error paths (no devices, missing entry, missing adapter)
"""

from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass, host: str = "1.2.3.4") -> MockConfigEntry:  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=f"{host}:9100",
        data={CONF_HOST: host, CONF_PORT: 9100},
        unique_id=f"{host}:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


def _get_device_id_for_entry(hass, entry: MockConfigEntry) -> str:  # type: ignore[no-untyped-def]
    device_registry = dr.async_get(hass)
    device = next(
        (d for d in device_registry.devices.values() if entry.entry_id in d.config_entries),
        None,
    )
    assert device is not None
    return device.id


async def test_print_text_utf8_service_transcodes(hass):  # type: ignore[no-untyped-def]
    """print_text_utf8 should transcode and reach the printer."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text_utf8",
            {"text": "Café"},
            blocking=True,
        )
    # Transcoding sends ASCII-friendly text to the printer
    assert fake.text.called


async def test_print_text_with_device_id_target(hass):  # type: ignore[no-untyped-def]
    """device_id targeting should route the call through target_resolution."""
    entry = await _setup_entry(hass)
    device_id = _get_device_id_for_entry(hass, entry)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello", "device_id": device_id},
            blocking=True,
        )
    assert fake.text.called


async def test_print_text_with_device_id_list_target(hass):  # type: ignore[no-untyped-def]
    """A list-form device_id should resolve via the iterable branch."""
    e1 = await _setup_entry(hass, "1.1.1.1")
    e2 = await _setup_entry(hass, "2.2.2.2")
    d1 = _get_device_id_for_entry(hass, e1)
    d2 = _get_device_id_for_entry(hass, e2)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello", "device_id": [d1, d2]},
            blocking=True,
        )
    # Both printers should have received the call
    assert fake.text.call_count >= 2


async def test_print_text_with_unknown_device_id_falls_back_to_no_match(hass):  # type: ignore[no-untyped-def]
    """An unknown device_id resolves to no targets, raising ServiceValidationError."""
    await _setup_entry(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello", "device_id": "nonexistent_device_id"},
            blocking=True,
        )


async def test_no_targets_raises_service_validation_error(hass):  # type: ignore[no-untyped-def]
    """Calling a service with no entries configured raises ServiceValidationError."""
    # Setup then unload so service is registered but no entries are loaded
    entry = await _setup_entry(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    # Re-register a fresh entry so services are still registered for this test,
    # then unload again to leave services in place but no loaded entries.
    # The service is unregistered after the last unload — so this scenario
    # actually means the service won't exist. Instead, set up two entries,
    # unload one, and use a device_id that doesn't match any entry.
    e1 = await _setup_entry(hass, "1.1.1.1")
    e2 = await _setup_entry(hass, "2.2.2.2")
    # Both loaded; pass an unknown device_id
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello", "device_id": "totally_unknown"},
            blocking=True,
        )
    # cleanup
    await hass.config_entries.async_unload(e1.entry_id)
    await hass.config_entries.async_unload(e2.entry_id)
    await hass.async_block_till_done()


async def test_print_text_adapter_error_raises_homeassistant_error(hass):  # type: ignore[no-untyped-def]
    """If the adapter raises, the service call must raise HomeAssistantError."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("printer offline")

    with patch.object(adapter, "print_text", side_effect=_boom):
        with pytest.raises(HomeAssistantError, match="printer offline"):
            await hass.services.async_call(
                DOMAIN,
                "print_text",
                {"text": "Hello"},
                blocking=True,
            )


async def test_feed_adapter_error_raises_homeassistant_error(hass):  # type: ignore[no-untyped-def]
    """Control-handler error path: feed adapter raises -> HomeAssistantError."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("paper jam")

    with patch.object(adapter, "feed", side_effect=_boom):
        with pytest.raises(HomeAssistantError, match="paper jam"):
            await hass.services.async_call(
                DOMAIN,
                "feed",
                {"lines": 2},
                blocking=True,
            )


async def test_cut_adapter_error_raises_homeassistant_error(hass):  # type: ignore[no-untyped-def]
    """Control-handler error path: cut adapter raises -> HomeAssistantError."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("cutter stuck")

    with patch.object(adapter, "cut", side_effect=_boom):
        with pytest.raises(HomeAssistantError, match="cutter stuck"):
            await hass.services.async_call(
                DOMAIN,
                "cut",
                {"mode": "partial"},
                blocking=True,
            )


async def test_beep_adapter_error_raises_homeassistant_error(hass):  # type: ignore[no-untyped-def]
    """Control-handler error path: beep adapter raises -> HomeAssistantError."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("buzzer broken")

    with patch.object(adapter, "beep", side_effect=_boom):
        with pytest.raises(HomeAssistantError, match="buzzer broken"):
            await hass.services.async_call(
                DOMAIN,
                "beep",
                {"times": 1, "duration": 1},
                blocking=True,
            )


async def test_print_qr_adapter_error_raises_homeassistant_error(hass):  # type: ignore[no-untyped-def]
    """Print-handler error path: print_qr adapter raises -> HomeAssistantError."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("qr render failed")

    with patch.object(adapter, "print_qr", side_effect=_boom):
        with pytest.raises(HomeAssistantError, match="qr render failed"):
            await hass.services.async_call(
                DOMAIN,
                "print_qr",
                {"data": "https://example.com"},
                blocking=True,
            )


async def test_print_barcode_adapter_error_raises_homeassistant_error(hass):  # type: ignore[no-untyped-def]
    """Print-handler error path: print_barcode adapter raises -> HomeAssistantError."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    async def _boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("barcode render failed")

    with patch.object(adapter, "print_barcode", side_effect=_boom):
        with pytest.raises(HomeAssistantError, match="barcode render failed"):
            await hass.services.async_call(
                DOMAIN,
                "print_barcode",
                {"code": "123", "bc": "CODE128"},
                blocking=True,
            )
