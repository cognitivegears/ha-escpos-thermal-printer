"""Tests for the calibration wizard's impl + width steps (options flow)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_NETWORK,
    DOMAIN,
)


def _make_entry(hass, *, loaded: bool = True) -> tuple[MockConfigEntry, MagicMock]:
    """A MockConfigEntry with a mock adapter wired onto runtime_data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    if loaded:
        entry.mock_state(hass, ConfigEntryState.LOADED)
    adapter = MagicMock()
    adapter.print_image = AsyncMock()
    adapter.print_text = AsyncMock()
    entry.runtime_data = SimpleNamespace(adapter=adapter)
    return entry, adapter


async def _open_calibrate(hass, entry):  # type: ignore[no-untyped-def]
    """Hop through the init menu to the calibrate step."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "calibrate"}
    )


async def test_calibrate_aborts_when_entry_not_loaded(hass):  # type: ignore[no-untyped-def]
    """Calibration requires a live adapter; an unloaded entry aborts."""
    entry, _adapter = _make_entry(hass, loaded=False)

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "abort"
    assert result["reason"] == "printer_not_ready"


async def test_calibrate_prints_impl_candidates_and_shows_form(hass):  # type: ignore[no-untyped-def]
    """Entering the impl step prints a labeled page per candidate, in order."""
    entry, adapter = _make_entry(hass)

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_impl"
    assert result.get("errors") in (None, {})

    assert adapter.print_text.await_count == 3
    texts = [call.kwargs["text"] for call in adapter.print_text.await_args_list]
    assert texts == ["TEST 1", "TEST 2", "TEST 3"]

    assert adapter.print_image.await_count == 3
    impls = [call.kwargs["impl"] for call in adapter.print_image.await_args_list]
    assert impls == ["bitImageRaster", "bitImageColumn", "graphics"]


async def test_impl_reprint_reprints_and_reshows_same_step(hass):  # type: ignore[no-untyped-def]
    """action: reprint re-runs the prints and stays on calibrate_impl."""
    entry, adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": [], "action": "reprint"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_impl"
    assert adapter.print_text.await_count == 6
    assert adapter.print_image.await_count == 6


async def test_impl_all_candidates_failing_shows_print_error(hass):  # type: ignore[no-untyped-def]
    """If every candidate fails to print, the form re-shows a print-failure error."""
    entry, adapter = _make_entry(hass)
    adapter.print_image.side_effect = RuntimeError("boom")

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_impl"
    assert result["errors"]["base"] == "calibration_print_failed"


async def test_impl_continue_stores_choice_and_advances_to_width(hass):  # type: ignore[no-untyped-def]
    """Continuing with a selection stores the first candidate and prints width bars."""
    entry, adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"impls_clean": ["bitImageColumn"], "action": "continue"},
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_width"

    # 3 impl-step prints already happened; width step adds 4 more (one per bar).
    assert adapter.print_image.await_count == 3 + 4
    width_calls = adapter.print_image.await_args_list[3:]
    assert len(width_calls) == 4
    assert all(call.kwargs["impl"] == "bitImageColumn" for call in width_calls)
