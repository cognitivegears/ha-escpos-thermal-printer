"""Calibration wizard steps: image implementation and width detection.

Each step follows a print-on-entry pattern: showing the form for the
first time (``user_input is None``) or re-showing it after a
``"reprint"`` action re-runs that step's test prints; only a
non-``"reprint"`` submission stores the choice and advances. Printer I/O
goes through the live adapter at ``self.config_entry.runtime_data.adapter``
-- pure pattern/data-URI generation lives in ``calibration.py``.
"""

from __future__ import annotations

import contextlib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components.persistent_notification import async_create as pn_create
from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from ..capabilities import get_profile_codepages
from ..const import (
    CONF_CODEPAGE,
    CONF_IMPL,
    CONF_LINE_WIDTH,
    CONF_PROFILE,
    CONF_WIDTH_PIXELS,
    DEFAULT_IMPL,
)
from ..security import sanitize_log_message
from .calibration import (
    CODEPAGE_CANDIDATES,
    CODEPAGE_SAMPLE,
    IMPL_CANDIDATES,
    WIDTH_CANDIDATES,
    build_ruler,
    build_share_url,
    checkerboard_data_uri,
    codepage_sample_line,
    width_bar_data_uri,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigFlowResult
    from homeassistant.core import HomeAssistant

    from .. import EscposConfigEntry

_LOGGER = logging.getLogger(__name__)

_IMPL_LABELS = {
    "bitImageRaster": "Pattern 1 (Raster)",
    "bitImageColumn": "Pattern 2 (Column)",
    "graphics": "Pattern 3 (Graphics)",
}
_ACTION_CHOICES = {"continue": "Continue", "reprint": "Reprint the test page"}
_CONFIRM_ACTION_CHOICES = {"start": "Start calibration", "cancel": "Cancel"}
# Derived from WIDTH_CANDIDATES so the bar numbers/labels can't drift out
# of sync with what _print_width_bars actually prints.
_WIDTH_CHOICES: dict[str, str] = {
    str(w): f"Bar {i} ({w})" for i, w in enumerate(WIDTH_CANDIDATES, start=1)
} | {"none": "Not sure / bars unclear"}
_CODEPAGE_ACTION_CHOICES = {
    "continue": "Continue",
    "reprint": "Reprint the test lines",
    "skip": "Skip this step",
}
_SUMMARY_ACTION_CHOICES = {
    "save": "Save calibration",
    "discard": "Discard (save nothing)",
}
# results-dict key -> options-storage const; only keys present in self._calib
# get merged in, so an unmeasured setting is never touched on save.
_CALIB_TO_CONF = {
    "impl": CONF_IMPL,
    "width_pixels": CONF_WIDTH_PIXELS,
    "line_width": CONF_LINE_WIDTH,
    "codepage": CONF_CODEPAGE,
}
_SHARE_LINK_MODEL_PLACEHOLDER = "YOUR-PRINTER-MODEL"


def _read_versions() -> tuple[str, str]:
    """Integration + python-escpos versions (blocking; run via executor).

    A lookup failure on either package must never crash the summary step;
    ``build_share_url`` already degrades a missing version to "?".
    """
    try:
        integration_version = pkg_version("ha-escpos-thermal-printer")
    except PackageNotFoundError:
        manifest_path = Path(__file__).resolve().parent.parent / "manifest.json"
        integration_version = json.loads(manifest_path.read_text())["version"]
    try:
        escpos_version = pkg_version("python-escpos")
    except PackageNotFoundError:
        escpos_version = "?"
    return integration_version, escpos_version


class CalibrationFlowMixin:
    """Wizard steps for the printer calibration flow (options-flow mixin).

    Expects to be mixed into a class that has ``hass``, ``config_entry``
    (an ``EscposConfigEntry``), and ``async_show_form``/``async_abort``
    (from ``FlowHandler``/``OptionsFlow``).
    """

    hass: HomeAssistant
    config_entry: EscposConfigEntry
    _calib: dict[str, Any]
    _calib_extra: dict[str, Any]

    async def async_step_calibrate(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Calibration wizard entry: guard on a loaded entry, then start at the confirm screen."""
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                reason="printer_not_ready"
            )
        self._calib = {}
        self._calib_extra = {}
        return await self.async_step_calibrate_confirm()

    async def async_step_calibrate_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Paper-cost confirmation shown before any test page is printed."""
        if user_input is not None:
            if user_input.get("action") == "cancel":
                return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                    reason="calibration_discarded"
                )
            return await self.async_step_calibrate_impl()

        schema = vol.Schema(
            {
                vol.Required("action", default="start"): vol.In(_CONFIRM_ACTION_CHOICES),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_confirm", data_schema=schema
        )

    def _calibration_adapter(self) -> Any | None:
        """Return the live printer adapter, or None if the entry is no longer loaded.

        The config entry can unload while the wizard is open in a browser
        tab (an HA restart, or a reload triggered from another tab) --
        every step that prints must check this before dereferencing
        ``runtime_data.adapter``, or a stale/missing ``runtime_data``
        crashes with AttributeError instead of aborting cleanly.
        """
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return None
        return self.config_entry.runtime_data.adapter

    async def _print_step_header(self, adapter: Any, title: str, instruction: str) -> None:
        """Print a compact on-paper title + one-line instruction.

        Both lines are kept under ~30 chars so they don't wrap even on
        32-column printers. Header failures are non-fatal — the test page
        still works without it, and the content prints have their own
        error handling.
        """
        with contextlib.suppress(Exception):
            await adapter.print_text(
                self.hass, text=f"= {title} =\n{instruction}\n", cut="none", feed=0
            )

    async def _print_step_trailer(self, adapter: Any, feed: int = 3) -> None:
        """Blank feed after a step's page so steps separate on the roll."""
        with contextlib.suppress(Exception):
            await adapter.print_text(self.hass, text="", cut="none", feed=feed)

    async def _print_impl_candidates(self, adapter: Any) -> bool:
        """Print a labeled test page per image-implementation candidate.

        Each candidate is attempted independently so one rejecting a
        transport-level command (e.g. "graphics") can't brick the rest
        of the wizard. Returns True if at least one candidate printed.
        """
        await self._print_step_header(
            adapter, "CALIBRATE 1/4: IMAGE MODE", "Check clean patterns in app"
        )
        any_ok = False
        for n, candidate in enumerate(IMPL_CANDIDATES, start=1):
            try:
                # Trailing \n is load-bearing: with feed=0, ESC/POS only
                # flushes the text line buffer on a newline or feed. Without
                # it, raster printers drop the buffered label and column
                # printers merge it into the pattern line (seen on RP850P).
                await adapter.print_text(self.hass, text=f"TEST {n}\n", cut="none", feed=0)
                await adapter.print_image(
                    self.hass,
                    image=checkerboard_data_uri(),
                    impl=candidate,
                    cut="none",
                    feed=1,
                    dither="threshold",
                    auto_resize=False,
                )
                any_ok = True
            except Exception as err:
                _LOGGER.warning(
                    "Calibration impl candidate %s failed to print: %s",
                    candidate,
                    sanitize_log_message(str(err)),
                )
                with contextlib.suppress(Exception):
                    await adapter.print_text(
                        self.hass, text=f"TEST {n}: FAILED TO SEND\n", cut="none", feed=0
                    )
        if any_ok:
            await self._print_step_trailer(adapter)
        return any_ok

    async def async_step_calibrate_impl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print the impl test pages, then let the user pick which printed cleanly."""
        errors: dict[str, str] = {}
        if user_input is None or user_input.get("action") == "reprint":
            adapter = self._calibration_adapter()
            if adapter is None:
                return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                    reason="printer_not_ready"
                )
            try:
                if not await self._print_impl_candidates(adapter):
                    errors["base"] = "calibration_print_failed"
            except Exception as err:
                _LOGGER.warning("Calibration impl step failed: %s", sanitize_log_message(str(err)))
                errors["base"] = "calibration_print_failed"
        else:
            selection = user_input.get("impls_clean", [])
            self._calib_extra["impls_clean"] = selection
            if not selection:
                # None of the patterns printed cleanly -- there's no
                # working image mode to measure width bars with, so skip
                # straight to the ruler step instead of clamping
                # width_pixels to a fallback impl's raster output.
                return await self.async_step_calibrate_ruler()
            self._calib["impl"] = next(c for c in IMPL_CANDIDATES if c in selection)
            return await self.async_step_calibrate_width()

        schema = vol.Schema(
            {
                vol.Optional("impls_clean", default=[]): cv.multi_select(_IMPL_LABELS),
                vol.Required("action", default="continue"): vol.In(_ACTION_CHOICES),
            }
        )
        if user_input is not None:
            # Reprint: keep the boxes the user already checked instead of
            # wiping them back to the schema defaults.
            # Exclude "action" -- suggesting the previous "reprint" value
            # would pre-select "Reprint the test page" again, turning one
            # extra Continue click into an accidental reprint loop.
            suggested = {k: v for k, v in user_input.items() if k != "action"}
            schema = self.add_suggested_values_to_schema(schema, suggested)  # type: ignore[attr-defined]
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_impl", data_schema=schema, errors=errors
        )

    async def _print_width_bars(self, adapter: Any) -> None:
        """Print one bar per candidate width, using the impl chosen so far."""
        await self._print_step_header(
            adapter, "CALIBRATE 2/4: WIDTH BARS", "First bar equal to bottom?"
        )
        impl = self._calib.get("impl") or getattr(adapter, "default_impl", None) or DEFAULT_IMPL
        for w in WIDTH_CANDIDATES:
            # width=w beats a narrower profile/opts width in the image
            # pipeline (process_image only ever downscales, never
            # upscales), so each bar prints at its true pixel width
            # instead of all four being clamped to the same width.
            await adapter.print_image(
                self.hass,
                image=width_bar_data_uri(w),
                impl=impl,
                width=w,
                cut="none",
                feed=1,
                auto_resize=False,
            )
        await self._print_step_trailer(adapter, feed=2)

    async def async_step_calibrate_width(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print the width bars, then let the user pick where they stop matching."""
        errors: dict[str, str] = {}
        if user_input is None or user_input.get("action") == "reprint":
            adapter = self._calibration_adapter()
            if adapter is None:
                return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                    reason="printer_not_ready"
                )
            try:
                await self._print_width_bars(adapter)
            except Exception as err:
                _LOGGER.warning("Calibration width step failed: %s", sanitize_log_message(str(err)))
                errors["base"] = "calibration_print_failed"
        else:
            choice = user_input.get("first_equal", "none")
            if choice != "none":
                self._calib["width_pixels"] = int(choice)
            return await self.async_step_calibrate_ruler()

        schema = vol.Schema(
            {
                vol.Required("first_equal", default="none"): vol.In(_WIDTH_CHOICES),
                vol.Required("action", default="continue"): vol.In(_ACTION_CHOICES),
            }
        )
        if user_input is not None:
            # Exclude "action" -- suggesting the previous "reprint" value
            # would pre-select "Reprint the test page" again, turning one
            # extra Continue click into an accidental reprint loop.
            suggested = {k: v for k, v in user_input.items() if k != "action"}
            schema = self.add_suggested_values_to_schema(schema, suggested)  # type: ignore[attr-defined]
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_width", data_schema=schema, errors=errors
        )

    async def async_step_calibrate_ruler(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print a column ruler, then let the user report where it stops matching."""
        errors: dict[str, str] = {}
        if user_input is None or user_input.get("action") == "reprint":
            adapter = self._calibration_adapter()
            if adapter is None:
                return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                    reason="printer_not_ready"
                )
            try:
                # On-paper instruction so the wrapped remainder lines are
                # explicitly ignorable without consulting the screen.
                await adapter.print_text(
                    self.hass,
                    text="= CALIBRATE 3/4: COLUMNS =\n1st line: last number + dots\n",
                    cut="none",
                    feed=0,
                )
                await adapter.print_text(
                    self.hass, text=build_ruler(96), cut="none", feed=3, wrap=False
                )
            except Exception as err:
                _LOGGER.warning("Calibration ruler step failed: %s", sanitize_log_message(str(err)))
                errors["base"] = "calibration_print_failed"
        else:
            marker = user_input.get("last_marker", 0)
            if 1 <= marker <= 15:
                errors["base"] = "line_width_out_of_range"
            else:
                if marker:
                    self._calib["line_width"] = marker
                return await self.async_step_calibrate_codepage()

        schema = vol.Schema(
            {
                vol.Required("last_marker", default=0): vol.All(
                    vol.Coerce(int), vol.Range(min=0, max=96)
                ),
                vol.Required("action", default="continue"): vol.In(_ACTION_CHOICES),
            }
        )
        if user_input is not None:
            # Exclude "action" -- suggesting the previous "reprint" value
            # would pre-select "Reprint the test page" again, turning one
            # extra Continue click into an accidental reprint loop.
            suggested = {k: v for k, v in user_input.items() if k != "action"}
            schema = self.add_suggested_values_to_schema(schema, suggested)  # type: ignore[attr-defined]
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_ruler", data_schema=schema, errors=errors
        )

    async def _get_codepage_candidates(self) -> tuple[str, ...]:
        """Codepage candidates the configured profile can actually switch to.

        ``get_profile_codepages`` already falls back to the common
        codepage list (a superset of every candidate here) when no
        profile is configured or the profile's own list is unknown, so
        intersecting is enough -- no separate "no profile" branch needed.
        Deliberately NO fallback to the full candidate tuple when the
        intersection is empty: that fallback is exactly the
        false-verification bug (a candidate printing under a codepage the
        profile can't switch to) this narrowing exists to prevent.
        """
        profile = self.config_entry.options.get(
            CONF_PROFILE, self.config_entry.data.get(CONF_PROFILE)
        )
        profile_codepages = await self.hass.async_add_executor_job(get_profile_codepages, profile)
        return tuple(cp for cp in CODEPAGE_CANDIDATES if cp in profile_codepages)

    async def _print_codepage_candidates(
        self, adapter: Any, candidates: tuple[str, ...]
    ) -> dict[str, int]:
        """Print a labeled sample line per codepage candidate.

        Each candidate is attempted independently -- one codepage the
        printer rejects can't brick the rest of the step. Returns the
        candidates that printed successfully, mapped to their line number.
        """
        await self._print_step_header(
            adapter, "CALIBRATE 4/4: ENCODING", "Check matching lines in app"
        )
        printed: dict[str, int] = {}
        for n, cp in enumerate(candidates, start=1):
            try:
                await adapter.print_text(
                    self.hass,
                    # The codepage name is plain ASCII, so it renders
                    # correctly under every candidate encoding — the paper
                    # then correlates directly with the checkbox labels
                    # without hopping back to the screen.
                    text=f"{n} {cp}: {codepage_sample_line(cp)}\n",
                    encoding=cp,
                    cut="none",
                    feed=0,
                )
                printed[cp] = n
            except Exception as err:
                _LOGGER.debug(
                    "Calibration codepage candidate %s failed to print: %s",
                    cp,
                    sanitize_log_message(str(err)),
                )
        if printed:
            await self._print_step_trailer(adapter)
        return printed

    async def async_step_calibrate_codepage(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print a sample line per codepage candidate, then record which match."""
        errors: dict[str, str] = {}
        candidates = await self._get_codepage_candidates()
        if not candidates:
            # The profile supports none of the candidates -- there's
            # nothing to test (and nothing to show a form for), so skip
            # straight to the summary instead of an empty/broken step.
            return await self.async_step_calibrate_summary()
        printed: dict[str, int] = {}
        if user_input is None or user_input.get("action") == "reprint":
            adapter = self._calibration_adapter()
            if adapter is None:
                return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                    reason="printer_not_ready"
                )
            try:
                printed = await self._print_codepage_candidates(adapter, candidates)
                if not printed:
                    errors["base"] = "calibration_print_failed"
            except Exception as err:
                _LOGGER.warning(
                    "Calibration codepage step failed: %s", sanitize_log_message(str(err))
                )
                errors["base"] = "calibration_print_failed"
        else:
            action = user_input.get("action", "continue")
            if action != "skip":
                selection = user_input.get("codepages_match", [])
                self._calib_extra["codepages_match"] = selection
                if selection:
                    self._calib["codepage"] = next(cp for cp in candidates if cp in selection)
            return await self.async_step_calibrate_summary()

        choices = {cp: f"Line {n}: {cp} — {codepage_sample_line(cp)}" for cp, n in printed.items()}
        schema = vol.Schema(
            {
                vol.Optional("codepages_match", default=[]): cv.multi_select(choices),
                vol.Required("action", default="continue"): vol.In(_CODEPAGE_ACTION_CHOICES),
            }
        )
        if user_input is not None:
            # Exclude "action" -- suggesting the previous "reprint" value
            # would pre-select "Reprint the test page" again, turning one
            # extra Continue click into an accidental reprint loop.
            suggested = {k: v for k, v in user_input.items() if k != "action"}
            schema = self.add_suggested_values_to_schema(schema, suggested)  # type: ignore[attr-defined]
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_codepage",
            data_schema=schema,
            errors=errors,
            description_placeholders={"sample": CODEPAGE_SAMPLE},
        )

    async def _calib_results(self) -> dict[str, Any]:
        """Measured-value dict for ``build_share_url`` (profile + versions included)."""
        profile = self.config_entry.options.get(
            CONF_PROFILE, self.config_entry.data.get(CONF_PROFILE)
        )
        integration_version, escpos_version = await self.hass.async_add_executor_job(_read_versions)
        return {
            **self._calib,
            **self._calib_extra,
            "profile": profile,
            "integration_version": integration_version,
            "escpos_version": escpos_version,
        }

    async def _save_calibration(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        """Merge measured values into the existing options and apply them.

        Only keys actually present in ``self._calib`` are applied, so a
        setting the user never measured (or skipped) is left untouched.

        Options are applied via ``async_update_entry`` + an explicit
        reload instead of ``async_create_entry``: create_entry ends the
        flow on the frontend's hardcoded "Options successfully saved."
        screen, whereas an abort screen renders our own text — which is
        the only way to show the share link *after* saving. A persistent
        notification carries the same link for after the dialog closes.
        """
        merged: dict[str, Any] = {**dict(self.config_entry.options)}
        for calib_key, conf_key in _CALIB_TO_CONF.items():
            if calib_key in self._calib:
                merged[conf_key] = self._calib[calib_key]

        if self.hass.config_entries.async_update_entry(self.config_entry, options=merged):
            # OptionsFlowWithReload only auto-reloads on create_entry;
            # this path ends in an abort, so reload explicitly.
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)

        if not self._calib:
            return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                reason="calibration_saved_no_changes"
            )

        model = user_input.get("model", "").strip() or _SHARE_LINK_MODEL_PLACEHOLDER
        share_url = build_share_url(model, await self._calib_results())
        pn_create(
            self.hass,
            f"[Open a prefilled GitHub issue]({share_url}) to contribute your printer's "
            "calibration results.",
            title="Printer calibration saved",
            notification_id=f"escpos_calibration_{self.config_entry.entry_id}",
        )
        return self.async_abort(  # type: ignore[attr-defined,no-any-return]
            reason="calibration_saved",
            description_placeholders={"share_url": share_url},
        )

    async def async_step_calibrate_summary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show measured results, then merge-save or discard.

        The share link itself is shown on the post-save abort screen
        (and in a persistent notification) — the model field here only
        feeds it.
        """
        if user_input is not None:
            if user_input.get("action", "save") == "save":
                return await self._save_calibration(user_input)
            return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                reason="calibration_discarded"
            )

        schema = vol.Schema(
            {
                vol.Optional("model", default=""): str,
                vol.Required("action", default="save"): vol.In(_SUMMARY_ACTION_CHOICES),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_summary",
            data_schema=schema,
            description_placeholders={
                "impl": str(self._calib.get("impl") or "unchanged"),
                "width_pixels": str(self._calib.get("width_pixels") or "unchanged"),
                "line_width": str(self._calib.get("line_width") or "unchanged"),
                "codepage": str(self._calib.get("codepage") or "unchanged"),
            },
        )
