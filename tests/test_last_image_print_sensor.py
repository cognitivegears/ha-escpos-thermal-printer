"""Tests for the last-image-print sensor's push updates.

The sensor used to poll the adapter's ImageStats every 5 minutes; it now
subscribes to the adapter's image-stats listener and has should_poll=False."""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.printer.config import NetworkPrinterConfig
from custom_components.escpos_printer.printer.network_adapter import NetworkPrinterAdapter
from custom_components.escpos_printer.sensor import LastImagePrintSensor

_PNG_1X1 = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAAAAAA6fptVAAAACklEQVR4nGNgAAAAAgABSK+kcQAAAABJRU5ErkJggg=="
)


class _FakeEntry:
    def __init__(self, adapter: Any = None) -> None:
        self.entry_id = "abc"
        self.title = "Printer"
        self.data: dict[str, Any] = {}
        if adapter is not None:
            self.runtime_data = MagicMock()
            self.runtime_data.adapter = adapter


def test_last_image_print_sensor_does_not_poll() -> None:
    assert LastImagePrintSensor(_FakeEntry()).should_poll is False  # type: ignore[arg-type]


def test_adapter_image_stats_listener_subscribe_and_unsubscribe() -> None:
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    calls: list[int] = []
    remove = adapter.add_image_stats_listener(lambda: calls.append(1))

    adapter._notify_image_stats()
    assert calls == [1]

    remove()
    remove()  # idempotent
    adapter._notify_image_stats()
    assert calls == [1]


def test_adapter_image_stats_listener_errors_are_isolated() -> None:
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    calls: list[int] = []

    def _bad() -> None:
        raise RuntimeError("listener bug")

    adapter.add_image_stats_listener(_bad)
    adapter.add_image_stats_listener(lambda: calls.append(1))
    adapter._notify_image_stats()
    assert calls == [1]


async def test_sensor_subscribes_and_writes_state_on_push() -> None:
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    sensor = LastImagePrintSensor(_FakeEntry(adapter))  # type: ignore[arg-type]
    sensor.async_write_ha_state = MagicMock()  # type: ignore[method-assign]

    await sensor.async_added_to_hass()
    assert len(adapter._image_stats_listeners) == 1

    adapter._image_stats.total_prints = 3
    adapter._image_stats.last_source_kind = "data_uri"
    adapter._notify_image_stats()

    sensor.async_write_ha_state.assert_called_once()
    assert sensor.native_value == 3
    assert sensor.extra_state_attributes["last_source_kind"] == "data_uri"

    await sensor.async_will_remove_from_hass()
    assert adapter._image_stats_listeners == []


async def test_print_image_pushes_success_and_failure() -> None:
    """A real print_image fires the listener on success, and again on a failure."""
    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="1.2.3.4"))
    printer = MagicMock()
    adapter._connect = lambda: printer  # type: ignore[method-assign]
    hass = MagicMock()

    async def _exec(fn: Any, *args: Any) -> Any:
        return fn(*args)

    hass.async_add_executor_job = AsyncMock(side_effect=_exec)
    snapshots: list[tuple[int, int]] = []
    adapter.add_image_stats_listener(
        lambda: snapshots.append(
            (adapter._image_stats.total_prints, adapter._image_stats.total_failures)
        )
    )

    await adapter.print_image(hass, image=_PNG_1X1)
    assert snapshots[-1] == (1, 0)

    printer.image.side_effect = OSError("paper jam")
    n = len(snapshots)
    with contextlib.suppress(Exception):
        await adapter.print_image(hass, image=_PNG_1X1)
    assert len(snapshots) > n
    assert snapshots[-1][1] == 1


async def test_sensor_state_updates_after_image_print_without_polling(hass: Any) -> None:
    """End to end: an image print updates the (enabled) sensor's state immediately."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    # The sensor is disabled by default; pre-register it enabled.
    er.async_get(hass).async_get_or_create(
        "sensor",
        DOMAIN,
        f"{entry.entry_id}_last_image_print",
        config_entry=entry,
        suggested_object_id="printer_last_image_print",
        disabled_by=None,
    )
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get("sensor.printer_last_image_print")
    assert state is not None
    assert state.state == "0"

    with patch("escpos.printer.Network", return_value=MagicMock()):
        await hass.services.async_call(DOMAIN, "print_image", {"image": _PNG_1X1}, blocking=True)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.printer_last_image_print")
    assert state is not None
    assert state.state == "1"
