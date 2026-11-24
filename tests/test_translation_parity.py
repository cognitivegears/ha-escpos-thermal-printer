"""Every translation must mirror ``strings.json``: same keys, same placeholders."""

import json
from pathlib import Path
import re

import pytest

_TRANSLATIONS = (
    Path(__file__).resolve().parent.parent / "custom_components/escpos_printer/translations"
)
_PLACEHOLDER = re.compile(r"\{[a-z_0-9]+\}")


def _leaves(node: object, prefix: str = "") -> dict[str, str]:
    if isinstance(node, str):
        return {prefix: node}
    if isinstance(node, dict):
        out: dict[str, str] = {}
        for key, value in node.items():
            out.update(_leaves(value, f"{prefix}.{key}" if prefix else key))
        return out
    return {}


_ENGLISH = _leaves(json.loads((_TRANSLATIONS / "en.json").read_text(encoding="utf-8")))
_OTHERS = sorted(p for p in _TRANSLATIONS.glob("*.json") if p.stem != "en")


def test_there_is_a_german_translation() -> None:
    assert (_TRANSLATIONS / "de.json").is_file()


@pytest.mark.parametrize("path", _OTHERS, ids=lambda p: p.stem)
def test_translation_has_exactly_the_keys_of_english(path: Path) -> None:
    translated = _leaves(json.loads(path.read_text(encoding="utf-8")))
    assert sorted(translated) == sorted(_ENGLISH)


@pytest.mark.parametrize("path", _OTHERS, ids=lambda p: p.stem)
def test_translation_keeps_every_placeholder(path: Path) -> None:
    translated = _leaves(json.loads(path.read_text(encoding="utf-8")))
    for key, english in _ENGLISH.items():
        assert sorted(_PLACEHOLDER.findall(translated[key])) == sorted(
            _PLACEHOLDER.findall(english)
        ), key


@pytest.mark.parametrize("path", _OTHERS, ids=lambda p: p.stem)
def test_translation_has_no_empty_texts(path: Path) -> None:
    translated = _leaves(json.loads(path.read_text(encoding="utf-8")))
    assert [key for key, text in translated.items() if not text.strip()] == []
