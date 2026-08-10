"""Tests for the calibration wizard's impl + width steps (options flow)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from homeassistant.components import persistent_notification as pn
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer._config_flow.calibration import CODEPAGE_CANDIDATES
from custom_components.escpos_printer.capabilities.loader import _get_capabilities
from custom_components.escpos_printer.const import (
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_IMPL,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_TIMEOUT,
    CONF_WIDTH_PIXELS,
    CONNECTION_TYPE_NETWORK,
    DOMAIN,
)


def test_read_versions_falls_back_to_manifest_json(monkeypatch):  # type: ignore[no-untyped-def]
    """A missing installed-package record must not crash the summary step --
    fall back to reading the version straight out of manifest.json."""
    from importlib.metadata import PackageNotFoundError
    import json
    from pathlib import Path

    from custom_components.escpos_printer._config_flow import calibration_steps

    def _raise_not_found(name):  # type: ignore[no-untyped-def]
        raise PackageNotFoundError(name)

    monkeypatch.setattr(calibration_steps, "pkg_version", _raise_not_found)

    integration_version, escpos_version = calibration_steps._read_versions()

    manifest_path = Path(calibration_steps.__file__).resolve().parent.parent / "manifest.json"
    expected_version = json.loads(manifest_path.read_text())["version"]
    assert integration_version == expected_version
    assert escpos_version == "?"


def test_codepage_candidates_are_real_encodings():
    """Every CODEPAGE_CANDIDATES entry must be a real, correctly-spelled encoding.

    A misspelled name (e.g. underscore vs hyphen) would still "print" --
    python-escpos swallows the charcode() failure inside print_operations'
    broad except -- so a bad spelling here is otherwise silently unverifiable.
    """
    real_encodings = set(_get_capabilities()["encodings"])
    missing = [cp for cp in CODEPAGE_CANDIDATES if cp not in real_encodings]
    assert not missing, f"CODEPAGE_CANDIDATES has unknown encoding name(s): {missing}"


def _make_entry(
    hass, *, loaded: bool = True, options: dict | None = None
) -> tuple[MockConfigEntry, MagicMock]:
    """A MockConfigEntry with a mock adapter wired onto runtime_data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_PORT: 9100,
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK,
        },
        options=options or {},
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
    """Hop through the init menu and the confirm screen to land on the impl step.

    If the entry isn't loaded, ``async_step_calibrate`` aborts before the
    confirm screen ever shows -- return that abort result as-is rather
    than submitting a second, now-nonexistent flow.
    """
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "calibrate"}
    )
    if result["type"] != "form" or result.get("step_id") != "calibrate_confirm":
        return result
    return await hass.config_entries.options.async_configure(result["flow_id"], {"action": "start"})


async def test_calibrate_aborts_when_entry_not_loaded(hass):  # type: ignore[no-untyped-def]
    """Calibration requires a live adapter; an unloaded entry aborts."""
    entry, _adapter = _make_entry(hass, loaded=False)

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "abort"
    assert result["reason"] == "printer_not_ready"


async def test_calibrate_shows_paper_cost_confirm_screen_first(hass):  # type: ignore[no-untyped-def]
    """The wizard's very first screen is the paper-cost confirmation --
    no test page is printed until the user starts it."""
    entry, adapter = _make_entry(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "calibrate"}
    )

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_confirm"
    assert adapter.print_text.await_count == 0
    assert adapter.print_image.await_count == 0


async def test_calibrate_confirm_cancel_aborts_without_printing(hass):  # type: ignore[no-untyped-def]
    """Cancelling the confirm screen aborts calibration_discarded, nothing printed."""
    entry, adapter = _make_entry(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "calibrate"}
    )

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"action": "cancel"}
    )

    assert result2["type"] == "abort"
    assert result2["reason"] == "calibration_discarded"
    assert adapter.print_text.await_count == 0
    assert adapter.print_image.await_count == 0


async def test_calibrate_confirm_start_advances_to_impl_step(hass):  # type: ignore[no-untyped-def]
    """Starting the confirm screen advances into the impl step (which prints)."""
    entry, adapter = _make_entry(hass)

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_impl"
    assert adapter.print_text.await_count == 3


async def test_calibrate_prints_impl_candidates_and_shows_form(hass):  # type: ignore[no-untyped-def]
    """Entering the impl step prints a labeled page per candidate, in order."""
    entry, adapter = _make_entry(hass)

    result = await _open_calibrate(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_impl"
    assert result.get("errors") in (None, {})

    assert adapter.print_text.await_count == 3
    texts = [call.kwargs["text"] for call in adapter.print_text.await_args_list]
    # Labels must carry their own newline: they print with feed=0, and
    # ESC/POS only flushes the text line buffer on a newline or feed —
    # without it, raster printers drop the buffered label entirely and
    # column printers merge it into the pattern line (seen on RP850P).
    assert texts == ["TEST 1\n", "TEST 2\n", "TEST 3\n"]

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


async def test_impl_reprint_preserves_checked_selection(hass):  # type: ignore[no-untyped-def]
    """Reprinting must not wipe the boxes the user already checked."""
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": ["bitImageColumn"], "action": "reprint"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_impl"
    schema = result2["data_schema"].schema
    impls_key = next(k for k in schema if k.schema == "impls_clean")
    assert impls_key.description == {"suggested_value": ["bitImageColumn"]}
    # The "reprint" action itself must NOT carry a suggested_value --
    # otherwise the frontend would pre-select "Reprint the test page"
    # again, turning a routine Continue click into an accidental
    # paper-burning reprint loop.
    action_key = next(k for k in schema if k.schema == "action")
    assert (
        action_key.description is None or action_key.description.get("suggested_value") != "reprint"
    )


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

    # 3 impl-step prints already happened; width step adds 5 more (one per bar).
    assert adapter.print_image.await_count == 3 + 5
    width_calls = adapter.print_image.await_args_list[3:]
    assert len(width_calls) == 5
    assert all(call.kwargs["impl"] == "bitImageColumn" for call in width_calls)
    # Each bar must request its own pixel width -- otherwise process_image
    # clamps every bar to the profile/opts width and they all print
    # identical length, making the step unable to measure anything wider.
    assert [call.kwargs["width"] for call in width_calls] == [384, 512, 576, 640, 832]


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
    assert fallback_texts == ["TEST 3: FAILED TO SEND\n"]


async def test_impl_empty_selection_skips_width_step(hass):  # type: ignore[no-untyped-def]
    """Continuing with no pattern checked skips straight to the ruler step.

    None of the image implementations printed cleanly, so the width-bar
    test (which needs a working image mode) can't measure anything --
    routing through it would just silently clamp width_pixels.
    """
    entry, adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    prints_before = adapter.print_image.await_count

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": [], "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_ruler"
    # No width-bar prints happened -- only the ruler step's own print (a
    # print_text call, not print_image).
    assert adapter.print_image.await_count == prints_before
    flow = hass.config_entries.options._progress[result2["flow_id"]]
    assert "width_pixels" not in flow._calib


async def test_width_bars_prefer_calib_impl_then_adapter_default(hass):  # type: ignore[no-untyped-def]
    """_print_width_bars: explicit user choice wins; adapter.default_impl is the fallback.

    The flow itself never reaches this fallback anymore (an unset impl
    now skips the width step entirely -- see
    test_impl_empty_selection_skips_width_step), so it's exercised
    directly against the helper.
    """
    entry, adapter = _make_entry(hass)
    adapter.default_impl = "bitImageColumn"
    result = await _open_calibrate(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    # User choice wins over adapter.default_impl.
    flow._calib["impl"] = "graphics"
    await flow._print_width_bars(adapter)
    assert all(
        call.kwargs["impl"] == "graphics" for call in adapter.print_image.await_args_list[-5:]
    )

    # No stored impl -- falls back to adapter.default_impl, not the
    # hardcoded "bitImageRaster".
    del flow._calib["impl"]
    await flow._print_width_bars(adapter)
    assert all(
        call.kwargs["impl"] == "bitImageColumn" for call in adapter.print_image.await_args_list[-5:]
    )


async def test_width_continue_with_bar_stores_pixels_then_advances_to_ruler(hass):  # type: ignore[no-untyped-def]
    """Picking a matching bar stores width_pixels and routes to the ruler step."""
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": ["bitImageRaster"], "action": "continue"}
    )
    flow = hass.config_entries.options._progress[result2["flow_id"]]

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {"first_equal": "576", "action": "continue"}
    )

    assert result3["type"] == "form"
    assert result3["step_id"] == "calibrate_ruler"
    assert flow._calib["width_pixels"] == 576


async def test_width_continue_with_none_stores_nothing_then_advances_to_ruler(hass):  # type: ignore[no-untyped-def]
    """ "Not sure / bars unclear" leaves width_pixels unset but still advances."""
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": ["bitImageRaster"], "action": "continue"}
    )
    flow = hass.config_entries.options._progress[result2["flow_id"]]

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {"first_equal": "none", "action": "continue"}
    )

    assert result3["type"] == "form"
    assert result3["step_id"] == "calibrate_ruler"
    assert "width_pixels" not in flow._calib


async def test_width_step_aborts_if_entry_unloads_mid_wizard(hass):  # type: ignore[no-untyped-def]
    """The entry can unload between showing a step's form and the user
    submitting it (HA restart, a reload triggered from another browser
    tab) -- the step must abort cleanly instead of crashing with
    AttributeError on a stale ``runtime_data.adapter`` reference.
    """
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": ["bitImageRaster"], "action": "continue"}
    )
    assert result2["step_id"] == "calibrate_width"

    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)

    result3 = await hass.config_entries.options.async_configure(
        result2["flow_id"], {"first_equal": "none", "action": "reprint"}
    )

    assert result3["type"] == "abort"
    assert result3["reason"] == "printer_not_ready"


async def _advance_to_ruler(hass, entry):  # type: ignore[no-untyped-def]
    """Hop through impl + width to land on the ruler step."""
    result = await _open_calibrate(hass, entry)
    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": ["bitImageRaster"], "action": "continue"}
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
    # wrap=False + 96 cols: the ruler measures the true printable width
    # instead of always breaking at the previously configured line_width.
    assert ruler_calls[0].kwargs.get("wrap") is False
    assert len(ruler_calls[0].kwargs["text"]) == 96


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


async def test_ruler_reprint_preserves_entered_marker(hass):  # type: ignore[no-untyped-def]
    """Reprinting must not wipe the marker value the user already entered."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_ruler(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 48, "action": "reprint"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_ruler"
    schema = result2["data_schema"].schema
    marker_key = next(k for k in schema if k.schema == "last_marker")
    assert marker_key.description == {"suggested_value": 48}


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


async def test_ruler_low_value_shows_line_width_out_of_range_error(hass):  # type: ignore[no-untyped-def]
    """1-15 is a positive number the user DID enter -- reject it with its own error key.

    ``invalid_line_width`` ("Must be a positive number") is wrong here:
    8 IS a positive number, it's just below the wizard's usable range.
    """
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_ruler(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 8, "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_ruler"
    assert result2["errors"]["base"] == "line_width_out_of_range"


async def test_codepage_step_prints_one_line_per_candidate_with_encoding(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """The codepage step prints one line per candidate, tagged with its encoding."""
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
    # Every feed=0 sample line needs its own newline, or unflushed lines
    # merge/drop on real hardware (same class as the impl-label bug).
    assert all(text.endswith("\n") for text in texts)


async def test_codepage_reprint_reprints(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """action: reprint re-prints the codepage lines and stays on calibrate_codepage."""
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
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_codepage(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"codepages_match": ["CP850", "CP858"], "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_summary"
    assert flow._calib["codepage"] == "CP858"
    assert flow._calib_extra["codepages_match"] == ["CP850", "CP858"]


async def test_codepage_skip_stores_nothing(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Skip stores neither codepages_match nor codepage."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_codepage(hass, entry)
    flow = hass.config_entries.options._progress[result["flow_id"]]

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"codepages_match": ["CP850"], "action": "skip"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_summary"
    assert "codepage" not in flow._calib
    assert "codepages_match" not in flow._calib_extra


async def test_codepage_choice_labels_carry_own_expected_rendering(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Each choice label shows what THAT candidate is expected to print.

    A CP437-class printer can't render the sample's '€' -- its own label
    must show the '?' substitution, or the accept criterion (exact match
    against a single shared reference) is impossible to satisfy on a
    correctly-working printer.
    """
    entry, _adapter = _make_entry(hass)

    result = await _advance_to_codepage(hass, entry)

    assert result["type"] == "form"
    labels = result["data_schema"].schema["codepages_match"].options
    assert labels["CP437"] == "Line 5: CP437 — café ñ ü é ß ° ?"
    assert labels["CP858"] == "Line 1: CP858 — café ñ ü é ß ° €"


async def test_codepage_all_candidates_failing_shows_print_error(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """If every candidate fails to print, the form re-shows a print-failure error."""
    entry, adapter = _make_entry(hass)
    adapter.print_text.side_effect = RuntimeError("boom")

    result = await _advance_to_codepage(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_codepage"
    assert result["errors"]["base"] == "calibration_print_failed"


async def test_codepage_candidates_narrowed_to_profile_using_real_capabilities_db(hass):  # type: ignore[no-untyped-def]
    """No monkeypatching: a real bundled profile (TM-T88II) narrows to its own codepages.

    TM-T88II's real codePages list omits CP858 and ISO_8859-1 -- this
    guards the narrowing logic against the real capabilities DB, not a
    fake stand-in.
    """
    entry, adapter = _make_entry(hass, options={CONF_PROFILE: "TM-T88II"})

    result = await _advance_to_codepage(hass, entry)

    assert result["type"] == "form"
    encodings = [
        call.kwargs["encoding"]
        for call in adapter.print_text.await_args_list
        if call.kwargs.get("encoding") is not None
    ]
    # Capability order (CODEPAGE_CANDIDATES), restricted to TM-T88II's real list.
    assert encodings == ["CP1252", "CP850", "CP437"]


async def test_codepage_step_skipped_when_profile_supports_none_of_the_candidates(hass):  # type: ignore[no-untyped-def]
    """AF-240's real codepage list (OXHOO-EUROPEAN) excludes all five candidates.

    No fallback to the full candidate list here -- that fallback IS the
    false-verification bug (printing a line under a codepage the printer
    can't actually switch to). With nothing left to test, the step is
    skipped entirely instead of showing a form with no working choices.
    """
    entry, adapter = _make_entry(hass, options={CONF_PROFILE: "AF-240"})
    result = await _advance_to_ruler(hass, entry)
    prints_before = adapter.print_text.await_count

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 0, "action": "continue"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_summary"
    assert adapter.print_text.await_count == prints_before


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


async def _advance_to_summary(  # type: ignore[no-untyped-def]
    hass, entry, *, codepage_action: str = "continue"
):
    """Hop through the full wizard chain to land on the summary step.

    Picks impl "bitImageColumn", width bar 576, ruler marker 48, and (unless
    ``codepage_action`` is "skip") codepage match "CP858".
    """
    result = await _open_calibrate(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": ["bitImageColumn"], "action": "continue"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"first_equal": "576", "action": "continue"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 48, "action": "continue"}
    )
    codepages_match = [] if codepage_action == "skip" else ["CP858"]
    return await hass.config_entries.options.async_configure(
        result["flow_id"],
        {"codepages_match": codepages_match, "action": codepage_action},
    )


async def test_full_wizard_save_merges_and_preserves_unrelated_option(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Save merges measured keys into options without dropping an unrelated one."""
    entry, _adapter = _make_entry(hass, options={CONF_TIMEOUT: 7.0})
    result = await _advance_to_summary(hass, entry)
    assert result["step_id"] == "calibrate_summary"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "", "action": "save"}
    )

    assert result2["type"] == "create_entry"
    data = result2["data"]
    assert data[CONF_TIMEOUT] == 7.0
    assert data[CONF_IMPL] == "bitImageColumn"
    assert data[CONF_WIDTH_PIXELS] == 576
    assert data[CONF_LINE_WIDTH] == 48
    assert data[CONF_CODEPAGE] == "CP858"


async def test_skip_codepage_then_save_omits_codepage_key(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Skipping the codepage step leaves CONF_CODEPAGE out of the saved options."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_summary(hass, entry, codepage_action="skip")

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "", "action": "save"}
    )

    assert result2["type"] == "create_entry"
    assert CONF_CODEPAGE not in result2["data"]
    assert result2["data"][CONF_WIDTH_PIXELS] == 576


async def test_save_creates_persistent_notification_with_share_link(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Saving posts a persistent notification carrying the share link.

    Save closes the flow, so the on-screen GitHub link disappears with
    it; the notification is the only place to find it again afterwards.
    """
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_summary(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "Rongta RP850P", "action": "save"}
    )

    assert result2["type"] == "create_entry"
    notifications = hass.data[pn.DOMAIN]
    notification_id = f"escpos_calibration_{entry.entry_id}"
    assert notification_id in notifications
    assert "Rongta%20RP850P" in notifications[notification_id][pn.ATTR_MESSAGE]


async def test_save_with_nothing_measured_creates_no_notification(hass):  # type: ignore[no-untyped-def]
    """A run where every step was skipped shouldn't advertise "(unchanged)" results."""
    entry, _adapter = _make_entry(hass)
    result = await _open_calibrate(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"impls_clean": [], "action": "continue"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"last_marker": 0, "action": "continue"}
    )
    assert result["step_id"] == "calibrate_codepage"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"codepages_match": [], "action": "skip"}
    )
    assert result["step_id"] == "calibrate_summary"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "", "action": "save"}
    )

    assert result2["type"] == "create_entry"
    assert not hass.data.get(pn.DOMAIN)


async def test_discard_creates_no_persistent_notification(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Discard doesn't post a notification -- nothing was saved to share."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_summary(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "", "action": "discard"}
    )

    assert result2["type"] == "abort"
    assert not hass.data.get(pn.DOMAIN)


async def test_discard_aborts_without_touching_options(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """Discard aborts the flow and leaves the entry's options untouched."""
    entry, _adapter = _make_entry(hass, options={CONF_TIMEOUT: 7.0})
    result = await _advance_to_summary(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "", "action": "discard"}
    )

    assert result2["type"] == "abort"
    assert result2["reason"] == "calibration_discarded"
    assert entry.options == {CONF_TIMEOUT: 7.0}


async def test_summary_description_placeholders_include_share_url_with_width(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """The summary form's share_url placeholder reflects the measured width."""
    entry, _adapter = _make_entry(hass)

    result = await _advance_to_summary(hass, entry)

    assert result["type"] == "form"
    assert result["step_id"] == "calibrate_summary"
    share_url = result["description_placeholders"]["share_url"]
    assert "576" in share_url


async def test_refresh_link_with_model_produces_url_with_encoded_model(hass, monkeypatch):  # type: ignore[no-untyped-def]
    """action: refresh_link re-renders the summary with the model baked into the URL."""
    entry, _adapter = _make_entry(hass)
    result = await _advance_to_summary(hass, entry)

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"], {"model": "Rongta RP850P", "action": "refresh_link"}
    )

    assert result2["type"] == "form"
    assert result2["step_id"] == "calibrate_summary"
    share_url = result2["description_placeholders"]["share_url"]
    assert "Rongta%20RP850P" in share_url
