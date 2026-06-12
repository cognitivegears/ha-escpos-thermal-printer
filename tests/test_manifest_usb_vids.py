"""Guard: manifest.json USB discovery VIDs must cover THERMAL_PRINTER_VIDS.

HA's USB discovery (manifest ``usb:`` matchers) and the config-flow
auto-discovery (``const.THERMAL_PRINTER_VIDS``) must agree on which
vendor IDs are thermal printers. They are maintained as two separate
lists; this test fails if the manifest is missing any VID the code
treats as a thermal printer (the two drifted once — 0x0FE6 was in
const.py but not the manifest).
"""

from __future__ import annotations

import json
from pathlib import Path

from custom_components.escpos_printer.const import THERMAL_PRINTER_VIDS

_MANIFEST = (
    Path(__file__).resolve().parent.parent
    / "custom_components"
    / "escpos_printer"
    / "manifest.json"
)


def test_manifest_usb_vids_cover_thermal_vids() -> None:
    manifest = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    manifest_vids = {int(entry["vid"], 16) for entry in manifest.get("usb", [])}
    missing = {f"0x{v:04X}" for v in THERMAL_PRINTER_VIDS if v not in manifest_vids}
    assert not missing, (
        f"manifest.json usb matchers are missing VIDs present in "
        f"THERMAL_PRINTER_VIDS: {sorted(missing)}"
    )
