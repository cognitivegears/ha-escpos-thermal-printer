"""Tests for the cover-open binary_sensor (DLE EOT n=2)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.escpos_printer.binary_sensor import (
    EscposCoverOpenSensor,
    EscposOnlineSensor,
    async_setup_entry,
)
from custom_components.escpos_printer.const import (
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
    CONNECTION_TYPE_NETWORK,
    CONNECTION_TYPE_SERIAL,
    CONNECTION_TYPE_USB,
)


class _FakeEntry:
    """Lightweight stand-in for ConfigEntry — only the attrs the sensors read."""

    def __init__(self, entry_id: str = "abc", data: dict[str, Any] | None = None) -> None:
        self.entry_id = entry_id
        self.data = data or {}


@pytest.mark.parametrize(
    ("connection_type", "expected"),
    [
        (CONNECTION_TYPE_NETWORK, True),
        (CONNECTION_TYPE_USB, True),
        (CONNECTION_TYPE_BLUETOOTH, False),
        (CONNECTION_TYPE_SERIAL, False),
    ],
)
async def test_setup_creates_cover_sensor_only_for_readable_transports(connection_type, expected):
    """BT/serial transports are write-only; an empty read would be a false 'closed'."""
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: connection_type})
    entry.runtime_data = MagicMock()
    add = MagicMock()
    await async_setup_entry(MagicMock(), entry, add)  # type: ignore[arg-type]
    entities = list(add.call_args.args[0])
    assert any(isinstance(e, EscposCoverOpenSensor) for e in entities) is expected
    # The online sensor is always created regardless of transport.
    assert any(isinstance(e, EscposOnlineSensor) for e in entities)


@pytest.mark.parametrize(
    ("status", "is_on", "available"),
    [(True, True, True), (False, False, True), (None, None, False)],
)
async def test_cover_sensor_reflects_adapter_status(status, is_on, available):
    entry = _FakeEntry(data={CONF_CONNECTION_TYPE: CONNECTION_TYPE_NETWORK})
    entry.runtime_data = MagicMock()
    entry.runtime_data.adapter.get_cover_status = AsyncMock(return_value=status)
    sensor = EscposCoverOpenSensor(entry)  # type: ignore[arg-type]
    sensor.hass = MagicMock()
    await sensor.async_update()
    assert sensor.available is available
    assert sensor.is_on is is_on


async def test_cover_sensor_unavailable_without_adapter():
    sensor = EscposCoverOpenSensor(_FakeEntry())  # type: ignore[arg-type]
    sensor.hass = MagicMock()
    await sensor.async_update()
    assert sensor.available is False


async def test_cover_sensor_unique_id_is_per_entry():
    assert EscposCoverOpenSensor(_FakeEntry("a")).unique_id == "a_cover_open"  # type: ignore[arg-type]
