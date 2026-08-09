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
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from ..capabilities import get_profile_codepages
from ..const import CONF_PROFILE
from ..security import sanitize_log_message
from .calibration import (
    CODEPAGE_CANDIDATES,
    CODEPAGE_SAMPLE,
    IMPL_CANDIDATES,
    WIDTH_CANDIDATES,
    build_ruler,
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
_WIDTH_CHOICES = {
    "384": "Bar 1 (384)",
    "512": "Bar 2 (512)",
    "576": "Bar 3 (576)",
    "640": "Bar 4 (640)",
    "none": "Not sure / bars unclear",
}
_CODEPAGE_ACTION_CHOICES = {
    "continue": "Continue",
    "reprint": "Reprint the test lines",
    "skip": "Skip this step",
}


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
        """Calibration wizard entry: guard on a loaded entry, then start at impl."""
        if self.config_entry.state is not ConfigEntryState.LOADED:
            return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                reason="printer_not_ready"
            )
        self._calib = {}
        self._calib_extra = {}
        return await self.async_step_calibrate_impl()

    async def _print_impl_candidates(self) -> bool:
        """Print a labeled test page per image-implementation candidate.

        Each candidate is attempted independently so one rejecting a
        transport-level command (e.g. "graphics") can't brick the rest
        of the wizard. Returns True if at least one candidate printed.
        """
        adapter = self.config_entry.runtime_data.adapter
        any_ok = False
        for n, candidate in enumerate(IMPL_CANDIDATES, start=1):
            try:
                await adapter.print_text(self.hass, text=f"TEST {n}", cut="none", feed=0)
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
                        self.hass, text=f"TEST {n}: FAILED TO SEND", cut="none", feed=0
                    )
        return any_ok

    async def async_step_calibrate_impl(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print the impl test pages, then let the user pick which printed cleanly."""
        errors: dict[str, str] = {}
        if user_input is None or user_input.get("action") == "reprint":
            try:
                if not await self._print_impl_candidates():
                    errors["base"] = "calibration_print_failed"
            except Exception as err:
                _LOGGER.warning(
                    "Calibration impl step failed: %s", sanitize_log_message(str(err))
                )
                errors["base"] = "calibration_print_failed"
        else:
            selection = user_input.get("impls_clean", [])
            self._calib_extra["impls_clean"] = selection
            if selection:
                self._calib["impl"] = next(c for c in IMPL_CANDIDATES if c in selection)
            return await self.async_step_calibrate_width()

        schema = vol.Schema(
            {
                vol.Optional("impls_clean", default=[]): cv.multi_select(_IMPL_LABELS),
                vol.Required("action", default="continue"): vol.In(_ACTION_CHOICES),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_impl", data_schema=schema, errors=errors
        )

    async def _print_width_bars(self) -> None:
        """Print one bar per candidate width, using the impl chosen so far."""
        adapter = self.config_entry.runtime_data.adapter
        impl = self._calib.get("impl", "bitImageRaster")
        for w in WIDTH_CANDIDATES:
            await adapter.print_image(
                self.hass,
                image=width_bar_data_uri(w),
                impl=impl,
                cut="none",
                feed=1,
                auto_resize=False,
            )

    async def async_step_calibrate_width(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print the width bars, then let the user pick where they stop matching."""
        errors: dict[str, str] = {}
        if user_input is None or user_input.get("action") == "reprint":
            try:
                await self._print_width_bars()
            except Exception as err:
                _LOGGER.warning(
                    "Calibration width step failed: %s", sanitize_log_message(str(err))
                )
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
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_width", data_schema=schema, errors=errors
        )

    async def async_step_calibrate_ruler(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print a column ruler, then let the user report where it stops matching."""
        errors: dict[str, str] = {}
        if user_input is None or user_input.get("action") == "reprint":
            try:
                adapter = self.config_entry.runtime_data.adapter
                await adapter.print_text(self.hass, text=build_ruler(64), cut="none", feed=1)
            except Exception as err:
                _LOGGER.warning(
                    "Calibration ruler step failed: %s", sanitize_log_message(str(err))
                )
                errors["base"] = "calibration_print_failed"
        else:
            marker = user_input.get("last_marker", 0)
            if 1 <= marker <= 15:
                errors["base"] = "invalid_line_width"
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
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_ruler", data_schema=schema, errors=errors
        )

    async def _get_codepage_candidates(self) -> tuple[str, ...]:
        """Codepage candidates, narrowed to the configured profile's list when possible."""
        profile = self.config_entry.options.get(
            CONF_PROFILE, self.config_entry.data.get(CONF_PROFILE)
        )
        profile_codepages = await self.hass.async_add_executor_job(
            get_profile_codepages, profile
        )
        narrowed = tuple(cp for cp in CODEPAGE_CANDIDATES if cp in profile_codepages)
        return narrowed or CODEPAGE_CANDIDATES

    async def _print_codepage_candidates(
        self, candidates: tuple[str, ...]
    ) -> dict[str, int]:
        """Print a labeled sample line per codepage candidate.

        Each candidate is attempted independently -- one codepage the
        printer rejects can't brick the rest of the step. Returns the
        candidates that printed successfully, mapped to their line number.
        """
        adapter = self.config_entry.runtime_data.adapter
        printed: dict[str, int] = {}
        for n, cp in enumerate(candidates, start=1):
            try:
                await adapter.print_text(
                    self.hass,
                    text=f"{n}: {codepage_sample_line(cp)}",
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
            await adapter.print_text(self.hass, text="", cut="none", feed=2)
        return printed

    async def async_step_calibrate_codepage(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Print a sample line per codepage candidate, then record which match."""
        errors: dict[str, str] = {}
        candidates = await self._get_codepage_candidates()
        if user_input is None or user_input.get("action") == "reprint":
            printed = await self._print_codepage_candidates(candidates)
            if not printed:
                errors["base"] = "calibration_print_failed"
        else:
            action = user_input.get("action", "continue")
            if action != "skip":
                selection = user_input.get("codepages_match", [])
                self._calib_extra["codepages_match"] = selection
                if selection:
                    self._calib["codepage"] = next(
                        cp for cp in candidates if cp in selection
                    )
            # Task 5 wires the summary; abort here for now.
            return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                reason="calibration_unavailable"
            )

        choices = {cp: f"Line {n}: {cp}" for cp, n in printed.items()}
        schema = vol.Schema(
            {
                vol.Optional("codepages_match", default=[]): cv.multi_select(choices),
                vol.Required("action", default="continue"): vol.In(
                    _CODEPAGE_ACTION_CHOICES
                ),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_codepage",
            data_schema=schema,
            errors=errors,
            description_placeholders={"sample": CODEPAGE_SAMPLE},
        )
