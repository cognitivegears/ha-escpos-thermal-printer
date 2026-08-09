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

from ..security import sanitize_log_message
from .calibration import (
    IMPL_CANDIDATES,
    WIDTH_CANDIDATES,
    checkerboard_data_uri,
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
            # Task 4 wires the next step (ruler); abort here for now.
            return self.async_abort(  # type: ignore[attr-defined,no-any-return]
                reason="calibration_unavailable"
            )

        schema = vol.Schema(
            {
                vol.Required("first_equal", default="none"): vol.In(_WIDTH_CHOICES),
                vol.Required("action", default="continue"): vol.In(_ACTION_CHOICES),
            }
        )
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="calibrate_width", data_schema=schema, errors=errors
        )
