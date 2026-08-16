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
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
import voluptuous as vol

from ..capabilities import get_profile_codepages, resolve_profile_name
from ..const import (
    CONF_CODEPAGE,
    CONF_DETECTED_MODEL,
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
_RULER_ACTION_CHOICES = _ACTION_CHOICES | {"skip": "Skip this step"}
_CONFIRM_ACTION_CHOICES = {"start": "Start calibration", "cancel": "Cancel"}
# Derived from WIDTH_CANDIDATES so the choices can't drift out of sync
# with what _print_width_bars actually prints.
_WIDTH_CHOICES: dict[str, str] = {str(w): f"{w} px" for w in WIDTH_CANDIDATES} | {
    "none": "None had an intact right edge"
}
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
            step_id="calibrate_confirm",
            data_schema=schema,
            # Used by the repairs fix-flow strings to name the printer; the
            # options-flow strings ignore it (already in device context).
            description_placeholders={"name": self.config_entry.title},
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

    async def _print_step_header(self, page: Any, title: str, instruction: str) -> None:
        """Print a compact on-paper title + one-line instruction.

        Both lines are kept under ~30 chars so they don't wrap even on
        32-column printers. Header failures are non-fatal — the test page
        still works without it, and the content prints have their own
        error handling.
        """
        with contextlib.suppress(Exception):
            await page.print_text(text=f"= {title} =\n{instruction}\n", feed=0)

    async def _print_step_trailer(self, page: Any, feed: int = 5) -> None:
        """Blank feed after a step's page so steps separate on the roll."""
        with contextlib.suppress(Exception):
            await page.feed(feed)

    async def _print_impl_candidates(self, adapter: Any) -> bool:
        """Print a labeled test page per image-implementation candidate.

        The whole page runs on one connection (``batch_connection``):
        with reconnect-per-operation, each label/pattern went out on its
        own short-lived TCP connection, and printers that accept the
        next connection before draining the previous one printed the
        fragments out of order (seen on TM-T20II: TEST 1/3/2).

        Each candidate is attempted independently so one rejecting a
        transport-level command (e.g. "graphics") can't brick the rest
        of the wizard. Returns True if at least one candidate printed.
        """
        any_ok = False
        async with adapter.batch_connection(self.hass) as page:
            await self._print_step_header(
                page, "CALIBRATE 1/4: IMAGE MODE", "Check clean patterns in app"
            )
            for n, candidate in enumerate(IMPL_CANDIDATES, start=1):
                try:
                    # Trailing \n is load-bearing: with feed=0, ESC/POS only
                    # flushes the text line buffer on a newline or feed. Without
                    # it, raster printers drop the buffered label and column
                    # printers merge it into the pattern line (seen on RP850P).
                    await page.print_text(text=f"TEST {n}\n", feed=0)
                    await page.print_image(
                        image=checkerboard_data_uri(),
                        impl=candidate,
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
                        await page.print_text(text=f"TEST {n}: FAILED TO SEND\n", feed=0)
            if any_ok:
                await self._print_step_trailer(page)
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

    async def _print_width_bars(self, adapter: Any) -> bool:
        """Print a labeled box per candidate width, using the impl chosen so far.

        Boxes wider than the printer's true width are the measurement —
        the hardware either clips or wraps them, losing the right-side
        border either way. That requires ``ignore_profile_width``:
        python-escpos otherwise refuses any image wider than the
        profile's declared ``media.width.pixels`` (``ImageWidthError``),
        which both broke the step on printers with a declared width
        (seen on TM-T20II @ 576: bars 640/832 aborted the page) and made
        an under-declared profile width impossible to detect. The width
        number is a separate text line above each box (not baked into
        the image) so the reader's only job is spotting an intact border,
        not reading two things at once. Each candidate is still attempted
        independently so a printer rejecting one can't abort the rest.
        Returns True if at least one candidate printed.
        """
        impl = self._calib.get("impl") or getattr(adapter, "default_impl", None) or DEFAULT_IMPL
        any_ok = False
        async with adapter.batch_connection(self.hass) as page:
            await self._print_step_header(
                page, "CALIBRATE 2/4: WIDTH BOXES", "Widest box with right edge?"
            )
            for w in WIDTH_CANDIDATES:
                try:
                    await page.print_text(text=f"{w}:\n", feed=0)
                    # width=w beats a narrower profile/opts width in the image
                    # pipeline (process_image only ever downscales, never
                    # upscales), so each box prints at its true pixel width
                    # instead of all of them being clamped to the same width.
                    # feed=2 (vs. the usual 1) keeps each label+box grouped
                    # and visibly separated from the next one.
                    await page.print_image(
                        image=width_bar_data_uri(w),
                        impl=impl,
                        width=w,
                        feed=2,
                        auto_resize=False,
                        ignore_profile_width=True,
                    )
                    any_ok = True
                except Exception as err:
                    _LOGGER.warning(
                        "Calibration width box %d failed to print: %s",
                        w,
                        sanitize_log_message(str(err)),
                    )
            if any_ok:
                await self._print_step_trailer(page, feed=4)
        return any_ok

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
                if not await self._print_width_bars(adapter):
                    errors["base"] = "calibration_print_failed"
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
                async with adapter.batch_connection(self.hass) as page:
                    # On-paper instruction so the wrapped remainder lines are
                    # explicitly ignorable without consulting the screen.
                    await page.print_text(
                        text="= CALIBRATE 3/4: COLUMNS =\n1st line: last number + dots\n",
                        feed=0,
                    )
                    await page.print_text(text=build_ruler(96), feed=5, wrap=False)
            except Exception as err:
                _LOGGER.warning("Calibration ruler step failed: %s", sanitize_log_message(str(err)))
                errors["base"] = "calibration_print_failed"
        else:
            if user_input.get("action") == "skip":
                return await self.async_step_calibrate_codepage()
            marker = user_input.get("last_marker")
            if marker is None:
                # "Continue" with an empty count is ambiguous -- make the
                # user either type what they measured or skip explicitly.
                errors["base"] = "line_width_missing"
            else:
                self._calib["line_width"] = marker
                return await self.async_step_calibrate_codepage()

        schema = vol.Schema(
            {
                # BOX mode: the user transcribes a count they just read off
                # the paper -- a typed number field, not a slider. 16 is the
                # narrowest plausible printer width; "don't know" is the
                # explicit skip action, not a magic 0.
                vol.Optional("last_marker"): vol.All(
                    NumberSelector(
                        NumberSelectorConfig(min=16, max=96, step=1, mode=NumberSelectorMode.BOX)
                    ),
                    vol.Coerce(int),
                ),
                vol.Required("action", default="continue"): vol.In(_RULER_ACTION_CHOICES),
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
        """Codepage candidates the *active* escpos profile can switch to.

        With no profile configured (or an unresolvable name), the printer
        object runs python-escpos's **default** profile, so candidates are
        filtered against that -- NOT the static ``COMMON_CODEPAGES`` list
        ``get_profile_codepages`` returns for those cases. That list
        includes ISO_8859-1, which the default profile cannot switch to:
        ``charcode()`` fails (silently, by design), the sample prints
        under the *previous* line's codepage, looks correct on paper, and
        the stored codepage then silently fails on every later print.
        Deliberately NO fallback to the full candidate tuple when the
        intersection is empty either, for the same reason: every printed
        line must be one the active profile can genuinely switch to.
        """
        profile = self.config_entry.options.get(
            CONF_PROFILE, self.config_entry.data.get(CONF_PROFILE)
        )
        resolved = await self.hass.async_add_executor_job(resolve_profile_name, profile)
        profile_codepages = await self.hass.async_add_executor_job(
            get_profile_codepages, resolved or "default"
        )
        return tuple(cp for cp in CODEPAGE_CANDIDATES if cp in profile_codepages)

    async def _print_codepage_candidates(
        self, adapter: Any, candidates: tuple[str, ...]
    ) -> dict[str, int]:
        """Print a labeled sample line per codepage candidate.

        Each candidate is attempted independently -- one codepage the
        printer rejects can't brick the rest of the step. Returns the
        candidates that printed successfully, mapped to their line number.
        """
        printed: dict[str, int] = {}
        async with adapter.batch_connection(self.hass) as page:
            await self._print_step_header(
                page, "CALIBRATE 4/4: ENCODING", "Check matching lines in app"
            )
            for n, cp in enumerate(candidates, start=1):
                try:
                    await page.print_text(
                        # The codepage name is plain ASCII, so it renders
                        # correctly under every candidate encoding — the paper
                        # then correlates directly with the checkbox labels
                        # without hopping back to the screen.
                        text=f"{n} {cp}: {codepage_sample_line(cp)}\n",
                        encoding=cp,
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
                await self._print_step_trailer(page)
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
                vol.Optional(
                    "model",
                    default=self.config_entry.data.get(CONF_DETECTED_MODEL, ""),
                ): str,
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
