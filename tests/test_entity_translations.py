"""Guard: entity translation_key values match icons.json's entity keys.

icons.json entries only take effect if their key matches an entity's
``translation_key`` — a stale/renamed key silently becomes dead JSON (this
happened with ``binary_sensor.status`` and ``sensor.battery``). This test
pins the translation_key on each entity class and cross-checks icons.json
so the two can't drift apart again.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

from custom_components.escpos_printer.binary_sensor import EscposOnlineSensor
from custom_components.escpos_printer.button import (
    EscposBeepButton,
    EscposCutButton,
    EscposFeedButton,
    EscposSamplePrintButton,
)
from custom_components.escpos_printer.sensor import (
    BluetoothPrinterBatterySensor,
    LastImagePrintSensor,
    PaperStatusSensor,
)

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "escpos_printer"


class _FakeEntry:
    """Lightweight stand-in for ConfigEntry — only the attrs entities read."""

    def __init__(self) -> None:
        self.entry_id = "abc"
        self.title = "Printer"
        self.data: dict[str, Any] = {}
        self.unique_id: str | None = None


def _make_entities() -> dict[str, Any]:
    adapter = MagicMock()
    adapter.get_status.return_value = None
    hass = MagicMock()
    return {
        "binary_sensor.online": EscposOnlineSensor(MagicMock(), _FakeEntry(), adapter),
        "sensor.last_image_print": LastImagePrintSensor(_FakeEntry()),
        "sensor.battery": BluetoothPrinterBatterySensor(_FakeEntry(), "AA:BB:CC:DD:EE:FF"),
        "sensor.paper_status": PaperStatusSensor(_FakeEntry()),
        "button.feed": EscposFeedButton(hass, _FakeEntry()),
        "button.cut": EscposCutButton(hass, _FakeEntry()),
        "button.beep": EscposBeepButton(hass, _FakeEntry()),
        "button.sample_print": EscposSamplePrintButton(hass, _FakeEntry()),
    }


def test_entities_have_expected_translation_keys() -> None:
    entities = _make_entities()
    for platform_and_key, entity in entities.items():
        _platform, expected_key = platform_and_key.split(".", 1)
        assert entity.translation_key == expected_key, platform_and_key


def test_icons_json_entity_keys_match_translation_keys() -> None:
    icons = json.loads((_COMPONENT_DIR / "icons.json").read_text(encoding="utf-8"))
    icon_keys = {
        (platform, key) for platform, entries in icons["entity"].items() for key in entries
    }
    translation_keys = {
        tuple(platform_and_key.split(".", 1)) for platform_and_key in _make_entities()
    }
    assert icon_keys <= translation_keys, (
        f"icons.json has entity keys with no matching translation_key: {icon_keys - translation_keys}"
    )
