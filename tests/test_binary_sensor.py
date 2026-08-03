"""Tests for the connectivity (online) binary_sensor.

Regression coverage for: a default install (status_interval=0, the
default) left the connectivity sensor at "unknown" until the first print
succeeded or failed, because the adapter never ran a status probe until
then and the entity's async_added_to_hass deliberately skipped one too.
base_adapter.EscposPrinterAdapterBase.start() now always runs a one-shot
initial probe, so get_status() is populated before the entity is even
constructed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.binary_sensor import EscposOnlineSensor
from custom_components.escpos_printer.const import DOMAIN


class _FakeEntry:
    """Lightweight stand-in for ConfigEntry — only the attrs the sensor reads."""

    def __init__(self, entry_id: str = "abc", data: dict[str, Any] | None = None) -> None:
        self.entry_id = entry_id
        self.data = data or {}


def test_online_sensor_picks_up_adapter_status_at_construction():
    """__init__ reads adapter.get_status() so an already-probed adapter isn't "unknown"."""
    adapter = MagicMock()
    adapter.get_status.return_value = True

    sensor = EscposOnlineSensor(MagicMock(), _FakeEntry(), adapter)  # type: ignore[arg-type]

    assert sensor.is_on is True


def test_online_sensor_stays_unset_when_adapter_never_probed():
    """A ``None`` status (never probed) leaves is_on unset, not forced False."""
    adapter = MagicMock()
    adapter.get_status.return_value = None

    sensor = EscposOnlineSensor(MagicMock(), _FakeEntry(), adapter)  # type: ignore[arg-type]

    assert getattr(sensor, "_attr_is_on", None) is None


async def test_online_binary_sensor_not_unknown_after_default_setup(hass):  # type: ignore[no-untyped-def]
    """A default install (status_interval=0) must not leave the sensor at "unknown".

    Exercises the real setup path end-to-end: base_adapter.start() runs a
    one-shot probe before platforms are forwarded, so by the time this
    entity is constructed, adapter.get_status() is already populated.
    """
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

    state = hass.states.get("binary_sensor.esc_pos_printer_1_2_3_4_9100_online")
    assert state is not None
    assert state.state != "unknown"
    # The recurring timer is still off by default; only the one-shot
    # initial probe ran.
    assert entry.runtime_data.adapter._cancel_status is None  # type: ignore[attr-defined]
