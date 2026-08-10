"""Guard: every ``errors["base"] = "..."`` key and ``async_abort(reason=...)``
reason set by the options flow (including the calibration wizard) exists
under strings.json's ``options.error`` / ``options.abort`` blocks.

Mirrors the pattern in test_exception_translations.py. Without an
``options.error``/``options.abort`` block, HA's lookup falls back to the
raw key (e.g. "invalid_profile") instead of the translated sentence.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "escpos_printer"
_OPTIONS_FLOW_FILES = (
    _COMPONENT_DIR / "_config_flow" / "options_flow.py",
    _COMPONENT_DIR / "_config_flow" / "calibration_steps.py",
)

_ERROR_BASE_RE = re.compile(r'errors\["base"\]\s*=\s*"([a-z0-9_]+)"')
_ABORT_REASON_RE = re.compile(r'async_abort\(\s*(?:#[^\n]*\n\s*)*reason\s*=\s*"([a-z0-9_]+)"')


def _matches_used(pattern: re.Pattern[str]) -> set[str]:
    found: set[str] = set()
    for path in _OPTIONS_FLOW_FILES:
        found |= set(pattern.findall(path.read_text(encoding="utf-8")))
    return found


def _error_keys_used() -> set[str]:
    return _matches_used(_ERROR_BASE_RE)


def _abort_reasons_used() -> set[str]:
    return _matches_used(_ABORT_REASON_RE)


def test_every_options_flow_error_exists_in_strings_json() -> None:
    used_keys = _error_keys_used()
    assert used_keys, "expected at least one errors['base'] assignment in the options flow files"
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    defined_keys = set(strings["options"]["error"])
    missing = used_keys - defined_keys
    assert not missing, (
        f"options-flow error key(s) missing from strings.json options.error: {missing}"
    )


def test_every_options_flow_abort_reason_exists_in_strings_json() -> None:
    used_reasons = _abort_reasons_used()
    assert used_reasons, "expected at least one async_abort(reason=...) in the options flow files"
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    defined_reasons = set(strings["options"]["abort"])
    missing = used_reasons - defined_reasons
    assert not missing, (
        f"options-flow abort reason(s) missing from strings.json options.abort: {missing}"
    )


def test_strings_json_and_en_json_options_match() -> None:
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((_COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    assert en["options"] == strings["options"]
