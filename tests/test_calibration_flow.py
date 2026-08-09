"""Tests for the calibration wizard's impl + width steps (options flow)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer._config_flow.calibration import CODEPAGE_CANDIDATES
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


async def test_impl_partial_candidate_failure_is_tolerated(hass):  # type: ignore[no-untyped-def]
    """One candidate (graphics) failing to send doesn't fail the whole step."""
    entry, adapter = _make_entry(hass)
    adapter.print_image.side_effect = [None, None, RuntimeError("boom")]

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_impl"
    assert result.get("errors") in (None, {})

    fallback_texts = [
        call.kwargs["text"]
        for call in adapter.print_text.await_args_list
        if "FAILED" in call.kwargs["text"]
    ]
    assert fallback_texts == ["TEST 3: FAILED TO SEND"]


async def test_width_continue_with_bar_stores_pixels_then_advances_to_ruler(hass):  # type: ignore[no-untyped-def]
    """Picking a matching bar stores width_pixels and routes to the ruler step."""
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": [], "action": "continue"}
    )
    flow = hass.config_entries.options._progress[result2["flow_id"]]

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {"first_equal": "576", "action": "continue"}
    )

    assert result3["type"] == "form"
    assert result3["step_id"] == "calibrate_ruler"
    assert flow._calib["width_pixels"] == 576


async def test_width_continue_with_none_stores_nothing_then_advances_to_ruler(hass):  # type: ignore[no-untyped-def]
    """"Not sure / bars unclear" leaves width_pixels unset but still advances."""
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": [], "action": "continue"}
    )
    flow = hass.config_entries.options._progress[result2["flow_id"]]

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {"first_equal": "none", "action": "continue"}
    )

    assert result3["type"] == "form"
    assert result3["step_id"] == "calibrate_ruler"
    assert "width_pixels" not in flow._calib


async def _advance_to_ruler(hass, entry):  # type: ignore[no-untyped-def]
    """Hop through impl + width to land on the ruler step."""
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": [], "action": "continue"}
    )
    return await hass.config_entries.options.async_configure(
        result2["flow_id"], {"first_equal": "none", "action": "continue"}
    )


async def _advance_to_codepage(hass, entry, *, last_marker: int = 0):  # type: ignore[no-untyped-def]
    """Hop through impl + width + ruler to land on the codepage step."""
    result = await _advance_to_ruler(hass, entry)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": last_marker, "action": "continue"}
    )


async def test_ruler_step_prints_once_and_shows_form(hass):  # type: ignore[no-untyped-def]
    """Entering the ruler step prints the column ruler once, plain ASCII."""
    entry, adapter = _make_entry(hass)

    result = await _advance_to_ruler(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_ruler"
    assert result.get("errors") in (None, {})
    ruler_calls = [
        call for call in adapter.print_text.await_args_list if "." in call.kwargs["text"]
    ]
    assert len(ruler_calls) == 1
    assert ruler_calls[0].kwargs.get("encoding") is None


async def test_ruler_reprint_reprints_and_reshows_same_step(hass):  # type: ignore[no-untyped-def]
    """action: reprint re-prints the ruler and stays on calibrate_ruler."""
    entry, adapter = _make_entry(hass)
    result = await _advance_to_ruler(hass, entry)
    before = adapter.print_text.await_count

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 0, "action": "reprint"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_ruler"
    assert adapter.print_text.await_count == before + 1


async def test_ruler_marker_stores_line_width_and_advances_to_codepage(hass):  # type: ignore[no-untyped-def]
    """A 16-96 marker value stores line_width and routes to the codepage step."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_ruler(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 48, "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_codepage"
    assert flow._calib["line_width"] == 48


async def test_ruler_zero_skips_storing_and_advances(hass):  # type: ignore[no-untyped-def]
    """0 (don't know / skip) leaves line_width unset but still advances."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_ruler(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 0, "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_codepage"
    assert "line_width" not in flow._calib


async def test_ruler_low_value_shows_invalid_line_width_error(hass):  # type: ignore[no-untyped-def]
    """1-15 is rejected with invalid_line_width and re-shows the ruler form."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_ruler(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 8, "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_ruler"
    assert result2["errors"]["base"] == "invalid_line_width"


async def test_codepage_step_prints_one_line_per_candidate_with_encoding(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """The codepage step prints one line per candidate, tagged with its encoding."""
    monkeypatch.setattr(
        "custom_components.escpos_printer._config_flow.calibration_steps.get_profile_codepages",
        lambda profile: [],
    )
    entry, adapter = _make_entry(hass)

    result = await _advance_to_codepage(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_codepage"
    assert result.get("errors") in (None, {})

    encodings = [
        call.kwargs["encoding"]
        for call in adapter.print_text.await_args_list
        if call.kwargs.get("encoding") is not None
    ]
    assert encodings == list(CODEPAGE_CANDIDATES)
    texts = [
        call.kwargs["text"]
        for call in adapter.print_text.await_args_list
        if call.kwargs.get("encoding") is not None
    ]
    assert texts[0].startswith("1: ")


async def test_codepage_reprint_reprints(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """action: reprint re-prints the codepage lines and stays on calibrate_codepage."""
    monkeypatch.setattr(
        "custom_components.escpos_printer._config_flow.calibration_steps.get_profile_codepages",
        lambda profile: [],
    )
    entry, adapter = _make_entry(hass)
    result = await _advance_to_codepage(hass, entry)
    before = adapter.print_text.await_count

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"codepages_match": [], "action": "reprint"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_codepage"
    assert adapter.print_text.await_count == before + len(CODEPAGE_CANDIDATES) + 1


async def test_codepage_continue_stores_first_in_candidate_order(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Multi-select ["CP850", "CP858"] stores "CP858" (capability order)."""
    monkeypatch.setattr(
        "custom_components.escpos_printer._config_flow.calibration_steps.get_profile_codepages",
        lambda profile: [],
    )
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_codepage(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"codepages_match": ["CP850", "CP858"], "action": "continue"}
    )

    assert result2["type"] == "abort"
    assert result2["reason"] == "calibration_unavailable"
    assert flow._calib["codepage"] == "CP858"
    assert flow._calib_extra["codepages_match"] == ["CP850", "CP858"]


async def test_codepage_skip_stores_nothing(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Skip stores neither codepages_match nor codepage."""
    monkeypatch.setattr(
        "custom_components.escpos_printer._config_flow.calibration_steps.get_profile_codepages",
        lambda profile: [],
    )
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_codepage(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"codepages_match": ["CP850"], "action": "skip"}
    )

    assert result2["type"] == "abort"
    assert result2["reason"] == "calibration_unavailable"
    assert "codepage" not in flow._calib
    assert "codepages_match" not in flow._calib_extra


async def test_codepage_all_candidates_failing_shows_print_error(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """If every candidate fails to print, the form re-shows a print-failure error."""
    monkeypatch.setattr(
        "custom_components.escpos_printer._config_flow.calibration_steps.get_profile_codepages",
        lambda profile: [],
    )
    entry, adapter = _make_entry(hass)
    adapter.print_text.side_effect = RuntimeError("boom")

    result = await _advance_to_codepage(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_codepage"
    assert result["errors"]["base"] == "calibration_print_failed"


async def test_codepage_profile_aware_narrowing(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """A profile with a restricted codepage list narrows the printed candidates."""
    monkeypatch.setattr(
        "custom_components.escpos_printer._config_flow.calibration_steps.get_profile_codepages",
        lambda profile: ["CP850", "CP437"],
    )
    entry, adapter = _make_entry(hass)

    result = await _advance_to_codepage(hass, entry)

    assert result["type"] == "form"
    encodings = [
        call.kwargs["encoding"]
        for call in adapter.print_text.await_args_list
        if call.kwargs.get("encoding") is not None
    ]
    # Capability order (CODEPAGE_CANDIDATES), restricted to the profile's list.
    assert encodings == ["CP850", "CP437"]
