"""Regression tests for scripts/check_version_sync.py.

The CHANGELOG-section guard was added alongside the version-match check:
CI must fail if manifest.json/pyproject.toml bump a version but
CHANGELOG.md never grew a matching ``## [<version>]`` heading.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

# Forces custom_components onto sys.path before the harness's autouse
# fixtures try to import the printer subpackage (see
# test_scripts_sync_manifest.py for the same pattern).
from custom_components.escpos_printer import const

_ = const

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"


def _load_module():
    sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop("check_version_sync", None)
    import check_version_sync

    return check_version_sync


def _write_project(
    tmp_path: pathlib.Path, *, manifest_version: str, pyproject_version: str, changelog_text: str
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"version": manifest_version}))
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(f'[project]\nversion = "{pyproject_version}"\n')
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(changelog_text)
    return manifest, pyproject, changelog


def test_passes_when_versions_match_and_changelog_documents_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_module()
    manifest, pyproject, changelog = _write_project(
        tmp_path,
        manifest_version="1.2.3",
        pyproject_version="1.2.3",
        changelog_text="## [Unreleased]\n\n## [1.2.3] - 2026-01-01\n",
    )
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    monkeypatch.setattr(mod, "PYPROJECT", pyproject)
    monkeypatch.setattr(mod, "CHANGELOG", changelog)

    assert mod.main() == 0


def test_fails_when_changelog_lacks_version_section(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    mod = _load_module()
    manifest, pyproject, changelog = _write_project(
        tmp_path,
        manifest_version="1.2.3",
        pyproject_version="1.2.3",
        changelog_text="## [Unreleased]\n",
    )
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    monkeypatch.setattr(mod, "PYPROJECT", pyproject)
    monkeypatch.setattr(mod, "CHANGELOG", changelog)

    assert mod.main() == 1
    assert "CHANGELOG.md has no" in capsys.readouterr().err


def test_fails_when_manifest_and_pyproject_versions_differ(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mod = _load_module()
    manifest, pyproject, changelog = _write_project(
        tmp_path,
        manifest_version="1.2.3",
        pyproject_version="1.2.4",
        changelog_text="## [1.2.3] - 2026-01-01\n## [1.2.4] - 2026-01-02\n",
    )
    monkeypatch.setattr(mod, "MANIFEST", manifest)
    monkeypatch.setattr(mod, "PYPROJECT", pyproject)
    monkeypatch.setattr(mod, "CHANGELOG", changelog)

    assert mod.main() == 1
