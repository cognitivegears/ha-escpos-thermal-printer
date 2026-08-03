"""Regression tests for ``scripts/sync_service_translations.py``.

strings.json's ``services`` key is generated from services.yaml so the two
can never drift (see CLAUDE.md "Service translations"). Mirrors the import
pattern in ``tests/test_scripts_sync_manifest.py``.
"""

from __future__ import annotations

import json
import pathlib
import sys
from types import ModuleType

import pytest

# Forces the test harness to wire ``custom_components`` into ``sys.path``
# before the autouse fixtures in ``conftest.py`` try to import the printer
# subpackage. The import itself is unused here.
from custom_components.escpos_printer import const

_ = const

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
COMPONENT = ROOT / "custom_components" / "escpos_printer"
STRINGS_JSON = COMPONENT / "strings.json"
EN_JSON = COMPONENT / "translations" / "en.json"


def _import_sync_module(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    # Anchor cwd to the repo root so the module's `ROOT = Path.cwd()`
    # resolves to the real project regardless of pytest's invocation dir.
    monkeypatch.chdir(ROOT)
    monkeypatch.syspath_prepend(str(SCRIPTS))
    sys.modules.pop("sync_service_translations", None)
    import sync_service_translations as mod

    return mod


def test_strings_json_services_matches_services_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    """Any services.yaml edit without a re-run of the sync script fails CI."""
    mod = _import_sync_module(monkeypatch)
    services_yaml = mod.yaml.safe_load(mod.SERVICES_YAML.read_text(encoding="utf-8"))
    regenerated = mod.build_services_section(services_yaml)

    committed = json.loads(STRINGS_JSON.read_text(encoding="utf-8"))
    assert committed.get("services") == regenerated, (
        "strings.json 'services' is out of sync with services.yaml; "
        "run `python scripts/sync_service_translations.py`"
    )


def test_en_json_is_byte_identical_to_strings_json() -> None:
    """translations/en.json must mirror strings.json byte-for-byte (English is the base locale)."""
    assert EN_JSON.read_bytes() == STRINGS_JSON.read_bytes()
