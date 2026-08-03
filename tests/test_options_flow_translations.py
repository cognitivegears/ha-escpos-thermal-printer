"""Guard: every ``errors["base"] = "..."`` key set by the options flow
exists under strings.json's ``options.error`` block.

Mirrors the pattern in test_exception_translations.py. Without an
``options.error`` block, HA's ``options.error.*`` lookup falls back to
the raw key (e.g. "invalid_profile") instead of the translated sentence.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "escpos_printer"
_OPTIONS_FLOW_FILE = _COMPONENT_DIR / "_config_flow" / "options_flow.py"

_ERROR_BASE_RE = re.compile(r'errors\["base"\]\s*=\s*"([a-z0-9_]+)"')


def _error_keys_used() -> set[str]:
    return set(_ERROR_BASE_RE.findall(_OPTIONS_FLOW_FILE.read_text(encoding="utf-8")))


def test_every_options_flow_error_exists_in_strings_json() -> None:
    used_keys = _error_keys_used()
    assert used_keys, "expected at least one errors['base'] assignment in options_flow.py"
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    defined_keys = set(strings["options"]["error"])
    missing = used_keys - defined_keys
    assert not missing, f"options-flow error key(s) missing from strings.json options.error: {missing}"


def test_strings_json_and_en_json_options_match() -> None:
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((_COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    assert en["options"] == strings["options"]
