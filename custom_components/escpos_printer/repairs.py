"""Repairs platform: fix flow for the printer-not-calibrated suggestion.

The fix flow IS the calibration wizard — ``CalibrationFlowMixin`` was
written flow-agnostic (needs only ``hass`` + ``config_entry``), so it
runs identically here and in the options flow.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.repairs import RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from ._config_flow.calibration_steps import CalibrationFlowMixin


class NotCalibratedRepairFlow(CalibrationFlowMixin, RepairsFlow):
    """Run the calibration wizard from Settings → Repairs."""

    def __init__(self, entry: Any) -> None:
        self.config_entry = entry
        self._calib: dict[str, Any] = {}
        self._calib_extra: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        return await self.async_step_calibrate()  # type: ignore[return-value]


async def async_create_fix_flow(
    hass: HomeAssistant, issue_id: str, data: dict[str, Any] | None
) -> RepairsFlow:
    entry = hass.config_entries.async_get_entry((data or {})["entry_id"])
    if entry is None:
        raise ValueError(f"Unknown config entry for repairs issue {issue_id}")
    return NotCalibratedRepairFlow(entry)
