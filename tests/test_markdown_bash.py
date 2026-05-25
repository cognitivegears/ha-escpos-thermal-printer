"""Tests for ``scripts/extract_markdown_bash.py``.

Two purposes:

1. Confirm the bundled ``blueprints/*.md`` markdown files pass the
   lint+smoke-exec sweep — same check that runs in pre-commit and CI.
2. Regression-guard the SIGPIPE-detection heuristic: a fixture with the
   exact unpatched ``tr | head`` pipeline must trigger a warning, and a
   fixture with the scoped ``set +o pipefail`` + assertion must pass.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from textwrap import dedent

# Forces the test harness to wire ``custom_components`` into ``sys.path``
# *before* the autouse ``fake_bluetooth_module`` fixture in
# ``conftest.py`` runs.
from custom_components.escpos_printer import const

_ = const  # keep the import live for ruff/mypy

REPO_ROOT = Path(__file__).resolve().parent.parent
BLUEPRINTS_DIR = REPO_ROOT / "blueprints"
EXTRACTOR_PATH = REPO_ROOT / "scripts" / "extract_markdown_bash.py"


def _load_extractor():
    spec = importlib.util.spec_from_file_location("extract_markdown_bash", EXTRACTOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_bundled_markdown_passes(capsys) -> None:  # type: ignore[no-untyped-def]
    """Every shipped ``blueprints/*.md`` must lint cleanly."""
    ex = _load_extractor()
    rc = ex.lint(BLUEPRINTS_DIR)
    captured = capsys.readouterr()
    assert rc == 0, f"extract_markdown_bash.py reported findings:\n{captured.err}"


def test_extractor_flags_unscoped_pipefail_password_generator(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """A markdown fixture that re-introduces the SIGPIPE bug must trip the warning.

    This is the regression guard for the bug class that shipped in
    ``UNIFI_GUEST_WIFI.md``: ``set -euo pipefail`` + ``tr -dc … | head
    -c 16`` exits 141 every run without the scoped ``set +o pipefail``.
    """
    ex = _load_extractor()
    fixture_root = tmp_path / "blueprints"
    fixture_root.mkdir()
    (fixture_root / "broken.md").write_text(
        dedent("""\
        # SIGPIPE regression fixture

        ```bash
        #!/usr/bin/env bash
        set -euo pipefail
        new_pass="$(LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' </dev/urandom | head -c 16)"
        echo "$new_pass"
        ```
        """),
        encoding="utf-8",
    )
    rc = ex.lint(fixture_root)
    assert rc != 0, "fixture with unscoped pipefail + tr|head must trip the warning"


def test_extractor_accepts_scoped_pipefail_password_generator(
    tmp_path,
) -> None:  # type: ignore[no-untyped-def]
    """The fixed pattern (scoped ``set +o pipefail`` + length assertion) must pass."""
    ex = _load_extractor()
    fixture_root = tmp_path / "blueprints"
    fixture_root.mkdir()
    (fixture_root / "fixed.md").write_text(
        dedent("""\
        # SIGPIPE fix fixture

        ```bash
        #!/usr/bin/env bash
        set -euo pipefail
        set +o pipefail
        new_pass="$(LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' </dev/urandom | head -c 16)"
        set -o pipefail
        [ "${#new_pass}" -eq 16 ] || {
            echo "password generation failed (got '$new_pass', expected 16 chars)" >&2
            exit 5
        }
        echo "$new_pass"
        ```
        """),
        encoding="utf-8",
    )
    rc = ex.lint(fixture_root)
    assert rc == 0, "fixture with scoped pipefail + length assertion must pass"
