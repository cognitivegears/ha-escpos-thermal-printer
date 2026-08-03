"""Guard: every ``translation_key`` raised in the service-error paths exists.

strings.json's ``exceptions`` section only takes effect if a raised
``ServiceValidationError``'s ``translation_key`` matches a key there — a
stale/renamed key silently falls back to the untranslated positional
message. This test greps the four files where Task 2 converted user-input
raises to ``ServiceValidationError`` and cross-checks every
``translation_key="..."`` literal against strings.json.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

_COMPONENT_DIR = Path(__file__).resolve().parent.parent / "custom_components" / "escpos_printer"

_SOURCE_FILES = (
    _COMPONENT_DIR / "security.py",
    _COMPONENT_DIR / "image_sources.py",
    _COMPONENT_DIR / "services" / "print_handlers.py",
    _COMPONENT_DIR / "services" / "target_resolution.py",
)

_TRANSLATION_KEY_RE = re.compile(r'translation_key\s*=\s*"([a-z0-9_]+)"')


def _translation_keys_used() -> set[str]:
    keys: set[str] = set()
    for path in _SOURCE_FILES:
        keys.update(_TRANSLATION_KEY_RE.findall(path.read_text(encoding="utf-8")))
    return keys


def test_every_raised_translation_key_exists_in_strings_json() -> None:
    used_keys = _translation_keys_used()
    assert used_keys, "expected at least one translation_key raise site"
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    defined_keys = set(strings["exceptions"])
    missing = used_keys - defined_keys
    assert not missing, f"translation_key(s) raised but missing from strings.json: {missing}"


def test_strings_json_and_en_json_exceptions_match() -> None:
    strings = json.loads((_COMPONENT_DIR / "strings.json").read_text(encoding="utf-8"))
    en = json.loads((_COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8"))
    assert en["exceptions"] == strings["exceptions"]
