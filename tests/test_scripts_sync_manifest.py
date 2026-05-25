"""Regression tests for the dependency-sync scripts.

Two bugs were patched together:

1. ``ROOT = Path(__file__).resolve().parents[1]`` made both scripts read
   the *script's* repo, not the caller's. The
   ``dependabot-auto-sync.yml`` workflow runs the script out of a
   trusted ``base/`` checkout against PR files under ``pr/``, so the old
   anchor silently no-op'd every manifest-affecting Dependabot PR (e.g.
   #90 wcwidth). The fix anchors to ``Path.cwd()``; these tests run the
   scripts as subprocesses with ``cwd=<tmp>`` to lock that in.

2. ``compatible()`` in ``check_requirements_sync.py`` checked a
   hand-maintained 7-element probe list of version strings instead of
   the actually-pinned version, so it couldn't detect drift outside
   that list (again, #90 wcwidth — neither 0.2.13 nor 0.7.0 was in the
   probes). The fix does a direct ``Version in SpecifierSet`` check;
   these tests cover the wcwidth-style case and the legitimate
   manifest-range case (e.g. ``Pillow``).
"""

from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import textwrap

from packaging.specifiers import SpecifierSet
import pytest

# Forces the test harness to wire ``custom_components`` into ``sys.path``
# before the autouse fixtures in ``conftest.py`` try to import the
# printer subpackage. The import itself is unused here.
from custom_components.escpos_printer import const

_ = const

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
CHECK_SCRIPT = SCRIPTS / "check_requirements_sync.py"
SYNC_SCRIPT = SCRIPTS / "sync_manifest_requirements.py"


def _make_project(
    root: pathlib.Path,
    *,
    pyproject_dep: str,
    manifest_dep: str,
    lock_version: str | None = None,
) -> None:
    """Lay out a minimal repo skeleton the scripts can read.

    Only the files the scripts touch — ``pyproject.toml``,
    ``manifest.json``, and optionally ``uv.lock`` — are written. The
    manifest path mirrors the real integration so the scripts find it
    without configuration.
    """
    (root / "pyproject.toml").write_text(
        textwrap.dedent(
            f"""\
            [project]
            name = "fake"
            version = "0.0.0"
            requires-python = ">=3.11"
            dependencies = [
              "{pyproject_dep}",
            ]
            """
        )
    )
    manifest_dir = root / "custom_components" / "escpos_printer"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "manifest.json").write_text(
        json.dumps({"domain": "fake", "requirements": [manifest_dep]}, indent=2) + "\n"
    )
    if lock_version is not None:
        name = pyproject_dep.split("=", 1)[0].split(">", 1)[0].split("<", 1)[0]
        (root / "uv.lock").write_text(
            textwrap.dedent(
                f"""\
                [[package]]
                name = "{name}"
                version = "{lock_version}"
                """
            )
        )


def _run(script: pathlib.Path, *args: str, cwd: pathlib.Path) -> subprocess.CompletedProcess[str]:
    """Run a script in ``cwd`` and capture its result.

    Subprocess (not import) because both scripts evaluate
    ``ROOT = Path.cwd()`` at module load — the fix's whole point is
    that ``cwd`` is what selects the project, so the test must control
    the working directory of a fresh interpreter.
    """
    return subprocess.run(  # noqa: S603 — args are test-controlled paths.
        [sys.executable, str(script), *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


class TestCwdAnchoredRoot:
    """The scripts must operate on ``cwd``, not the script's own repo."""

    def test_check_script_reads_cwd_project(self, tmp_path: pathlib.Path) -> None:
        _make_project(tmp_path, pyproject_dep="wcwidth==0.7.0", manifest_dep="wcwidth==0.7.0")
        result = _run(CHECK_SCRIPT, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        assert "in sync" in result.stdout

    def test_check_script_detects_drift_in_cwd_project(self, tmp_path: pathlib.Path) -> None:
        # Mismatch the real repo will never have: drift in the tmpdir.
        # If the script were still reading its own repo, it would see
        # main's (matching) state and falsely pass.
        _make_project(tmp_path, pyproject_dep="wcwidth==0.7.0", manifest_dep="wcwidth==0.2.13")
        result = _run(CHECK_SCRIPT, cwd=tmp_path)
        assert result.returncode != 0
        assert "wcwidth" in (result.stdout + result.stderr).lower()

    def test_sync_script_writes_cwd_manifest(self, tmp_path: pathlib.Path) -> None:
        _make_project(
            tmp_path,
            pyproject_dep="wcwidth==0.7.0",
            manifest_dep="wcwidth==0.2.13",
            lock_version="0.7.0",
        )
        manifest_path = tmp_path / "custom_components" / "escpos_printer" / "manifest.json"
        before = manifest_path.read_text()
        result = _run(SYNC_SCRIPT, cwd=tmp_path)
        assert result.returncode == 0, result.stdout + result.stderr
        after = manifest_path.read_text()
        assert "wcwidth==0.7.0" in after
        assert before != after, "sync script must update the cwd manifest, not main's"

    def test_sync_check_mode_flags_drift_in_cwd_project(self, tmp_path: pathlib.Path) -> None:
        _make_project(
            tmp_path,
            pyproject_dep="wcwidth==0.7.0",
            manifest_dep="wcwidth==0.2.13",
            lock_version="0.7.0",
        )
        result = _run(SYNC_SCRIPT, "--check", cwd=tmp_path)
        assert result.returncode != 0
        assert "wcwidth" in result.stdout.lower()

    def test_workflow_invocation_pattern(self, tmp_path: pathlib.Path) -> None:
        """Mirror dependabot-auto-sync.yml: script copy in ``base/``, PR
        files in ``pr/``, invocation from inside ``pr/``. This is the
        exact shape that silently failed on #90; without the ROOT fix
        the script would have written ``base/``'s manifest instead.
        """
        base = tmp_path / "base"
        pr = tmp_path / "pr"
        (base / "scripts").mkdir(parents=True)
        pr.mkdir()
        shutil.copy(SYNC_SCRIPT, base / "scripts" / SYNC_SCRIPT.name)
        _make_project(
            pr,
            pyproject_dep="wcwidth==0.7.0",
            manifest_dep="wcwidth==0.2.13",
            lock_version="0.7.0",
        )
        # Also stage a "base" project to detect cross-writes: if the
        # script still anchored to __file__, it would update *this*
        # manifest, not the PR's.
        _make_project(base, pyproject_dep="wcwidth==0.2.13", manifest_dep="wcwidth==0.2.13")
        result = _run(base / "scripts" / SYNC_SCRIPT.name, cwd=pr)
        assert result.returncode == 0, result.stdout + result.stderr
        pr_manifest = json.loads(
            (pr / "custom_components" / "escpos_printer" / "manifest.json").read_text()
        )
        base_manifest = json.loads(
            (base / "custom_components" / "escpos_printer" / "manifest.json").read_text()
        )
        assert pr_manifest["requirements"] == ["wcwidth==0.7.0"]
        assert base_manifest["requirements"] == ["wcwidth==0.2.13"], (
            "script must not write the base/main checkout — that's the supply-chain "
            "boundary the workflow's two-checkout dance protects"
        )


class TestCompatibleVersionMembership:
    """``compatible()`` must use real version membership, not a probe list."""

    @pytest.fixture(autouse=True)
    def _import_check_module(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
    ) -> None:
        # The module evaluates ``ROOT = Path.cwd()`` at import; point it
        # at a benign empty project so the import doesn't read main's
        # files (or fail if run elsewhere).
        _make_project(tmp_path, pyproject_dep="wcwidth==0.7.0", manifest_dep="wcwidth==0.7.0")
        monkeypatch.chdir(tmp_path)
        monkeypatch.syspath_prepend(str(SCRIPTS))
        # Force a fresh import so the module-level ROOT reflects our cwd.
        sys.modules.pop("check_requirements_sync", None)

    def test_pinned_version_inside_range_is_compatible(self) -> None:
        import check_requirements_sync as mod

        # Real-world example: pyproject pins Pillow exactly to HA's
        # bundled version while manifest carries the wider range we ship
        # so HA's resolver doesn't fight us.
        assert mod.compatible(SpecifierSet("==12.1.1"), SpecifierSet(">=12.1.1,<13.0.0"))

    def test_pinned_version_outside_range_is_incompatible(self) -> None:
        import check_requirements_sync as mod

        # The regression: old probe-list compatible() said True here
        # because neither 0.2.13 nor 0.7.0 was in the probes, so the
        # all(...) over an empty-of-mismatches list trivially passed.
        assert not mod.compatible(SpecifierSet("==0.7.0"), SpecifierSet("==0.2.13"))

    def test_equal_pins_are_compatible(self) -> None:
        import check_requirements_sync as mod

        assert mod.compatible(SpecifierSet("==0.7.0"), SpecifierSet("==0.7.0"))

    def test_empty_manifest_spec_is_wildcard(self) -> None:
        import check_requirements_sync as mod

        # Manifest deps without specifiers are accepted by HA's
        # resolver as "any version"; treat as compatible to match.
        assert mod.compatible(SpecifierSet("==0.7.0"), SpecifierSet(""))

    def test_pinned_version_outside_upper_bound_is_incompatible(self) -> None:
        import check_requirements_sync as mod

        # Manifest range deliberately caps below pyproject pin —
        # represents the "we bumped pyproject but forgot to widen
        # manifest" class of drift.
        assert not mod.compatible(SpecifierSet("==13.0.0"), SpecifierSet(">=12.1.1,<13.0.0"))
