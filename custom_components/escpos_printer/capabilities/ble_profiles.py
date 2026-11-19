"""Built-in profiles for raster printers using Bluetooth LE."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
import json
from pathlib import Path
import re
from typing import Literal

CRAFTSCO_4777_DIALECT = "craftsco_4777"
_CRAFTSCO_4777_LEGACY = "crafts&co|4777"
_CRAFTSCO_4777_AIYIN = "crafts&co_4777"
type CraftsCo4777Variant = Literal["compressed", "lujiang", "aiyin"]


def is_craftsco_4777_name(name: str) -> bool:
    """Recognize both Bluetooth names shipped under article 4777."""
    return name.casefold().startswith((_CRAFTSCO_4777_LEGACY, _CRAFTSCO_4777_AIYIN))


def craftsco_4777_variant(name: str, model: str) -> CraftsCo4777Variant | None:
    """Resolve firmware as the Fichero app does for the two 4777 advertisements."""
    advertised = (name if is_craftsco_4777_name(name) else model).casefold()
    if advertised.startswith(_CRAFTSCO_4777_AIYIN):
        return "aiyin"
    if model.upper().startswith("D1_LJ20C_"):
        return "lujiang"
    if advertised.startswith(_CRAFTSCO_4777_LEGACY):
        return "compressed"
    return None


def _model_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


@dataclass(frozen=True, slots=True)
class BlePrinterProfile:
    """Geometry, advertisement names, and command family of a BLE printer."""

    name: str
    width: int
    dialect: str
    label_rows: int = 0
    advertisement_prefixes: tuple[str, ...] = ()
    model_names: tuple[str, ...] = ()

    def matches_advertisement(self, name: str) -> bool:
        """Return whether the advertised name suggests this profile."""
        return name.casefold().startswith(tuple(n.casefold() for n in self.advertisement_prefixes))

    def matches_model(self, name: str) -> bool:
        """Match the printer's response to the model query."""
        return not self.model_names or _model_key(name) in {
            _model_key(model) for model in self.model_names
        }


@cache
def get_ble_profiles() -> dict[str, BlePrinterProfile]:
    """Read the bundled BLE profiles (call in an executor)."""
    profiles = {
        "luckprinter_384": BlePrinterProfile(
            name="LuckPrinter (384 dots, continuous paper)", width=384, dialect="lujiang"
        ),
    }
    for path in sorted(Path(__file__).with_name("ble_profiles").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        profiles[path.stem] = BlePrinterProfile(
            name=data["name"],
            width=data["width"],
            dialect=data["dialect"],
            label_rows=data.get("label_rows", 0),
            advertisement_prefixes=tuple(data.get("advertisement_prefixes", ())),
            model_names=tuple(data.get("model_names", ())),
        )
    return profiles
