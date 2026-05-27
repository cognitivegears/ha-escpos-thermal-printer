"""Smoke test for bundled HA blueprints.

Defers to ``scripts/validate_blueprints.py`` so the same check runs in
CI and from the command line. The test only asserts that every YAML
file under ``blueprints/`` parses and exposes the required
``blueprint.*`` fields — full HA blueprint loading is out of scope.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# Forces the test harness to wire ``custom_components`` into ``sys.path``
# *before* the autouse ``fake_bluetooth_module`` fixture in
# ``conftest.py`` tries to import the printer subpackage. The import
# itself is otherwise unused by these tests.
from custom_components.escpos_printer import const

_ = const  # keep the import live for ruff/mypy

REPO_ROOT = Path(__file__).resolve().parent.parent
BLUEPRINTS_DIR = REPO_ROOT / "blueprints"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate_blueprints.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("validate_blueprints", VALIDATOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_blueprints_directory_exists() -> None:
    assert BLUEPRINTS_DIR.is_dir(), f"missing {BLUEPRINTS_DIR}"


def test_all_blueprints_parse_and_have_required_fields() -> None:
    validator = _load_validator()
    failures: dict[str, list[str]] = {}
    files = sorted(BLUEPRINTS_DIR.rglob("*.yaml"))
    assert files, "no blueprint files found — directory layout regressed?"
    for f in files:
        errors = validator.validate_file(f)
        if errors:
            failures[str(f.relative_to(REPO_ROOT))] = errors
    assert not failures, f"blueprints with structural problems: {failures}"


def test_validator_rejects_missing_blueprint_key(tmp_path) -> None:  # type: ignore[no-untyped-def]
    validator = _load_validator()
    bad = tmp_path / "broken.yaml"
    bad.write_text("just_a_dict: 1\n")
    errors = validator.validate_file(bad)
    assert any("blueprint" in e for e in errors)


def test_validator_rejects_bad_domain(tmp_path) -> None:  # type: ignore[no-untyped-def]
    validator = _load_validator()
    bad = tmp_path / "broken.yaml"
    bad.write_text("blueprint:\n  name: x\n  description: x\n  domain: not_a_domain\n  input: {}\n")
    errors = validator.validate_file(bad)
    assert any("domain" in e for e in errors)


def test_validator_flags_unknown_service(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Service-call lint: typo in service name must surface.

    Regression guard for the class of bug Phase 4 of the comprehensive
    review flagged — `escpos_printer.print_text_utf` (missing `8`) or
    `escpos_printer.print_qrcode` (wrong name) would have passed YAML
    structural validation and failed at runtime in user installs.
    """
    validator = _load_validator()
    # Build a blueprint structure under the repo's actual layout so the
    # validator finds the real services.yaml (relative to this file).
    bp_dir = REPO_ROOT / "blueprints" / "automation" / "escpos_printer"
    bp = tmp_path / "blueprints" / "automation" / "escpos_printer"
    bp.mkdir(parents=True)
    bad_blueprint = bp / "bad.yaml"
    bad_blueprint.write_text(
        "blueprint:\n"
        "  name: x\n"
        "  description: x\n"
        "  domain: automation\n"
        "  input: {}\n"
        "trigger: []\n"
        "action:\n"
        "  - service: escpos_printer.print_text_utf\n"  # typo, missing '8'
        "    data:\n"
        "      text: hi\n"
    )
    # Symlink custom_components into the temp layout so services.yaml is
    # reachable via the validator's upward walk.
    (tmp_path / "custom_components").symlink_to(
        REPO_ROOT / "custom_components", target_is_directory=True
    )
    errors = validator.validate_file(bad_blueprint, root=tmp_path / "blueprints")
    assert any("print_text_utf" in e and "not declared" in e for e in errors), (
        f"expected service-typo finding, got: {errors}"
    )
    # Sanity check that the original blueprints still pass when the same
    # symlinked services.yaml is reachable — ensures the lint isn't
    # over-eager.
    _ = bp_dir  # quiet "unused" hint
    real_errors = validator.validate_file(
        REPO_ROOT / "blueprints" / "automation" / "escpos_printer" / "todo_ticket.yaml",
        root=REPO_ROOT / "blueprints",
    )
    assert not real_errors, f"todo_ticket.yaml unexpectedly failed: {real_errors}"


def test_validator_flags_unknown_data_field(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Service-call lint: unknown data field on a valid service must surface."""
    validator = _load_validator()
    bp = tmp_path / "blueprints" / "automation" / "escpos_printer"
    bp.mkdir(parents=True)
    bad_blueprint = bp / "bad.yaml"
    bad_blueprint.write_text(
        "blueprint:\n"
        "  name: x\n"
        "  description: x\n"
        "  domain: automation\n"
        "  input: {}\n"
        "trigger: []\n"
        "action:\n"
        "  - service: escpos_printer.print_box\n"
        "    data:\n"
        "      text: hi\n"
        "      not_a_real_field: yes\n"  # bogus field
    )
    (tmp_path / "custom_components").symlink_to(
        REPO_ROOT / "custom_components", target_is_directory=True
    )
    errors = validator.validate_file(bad_blueprint, root=tmp_path / "blueprints")
    assert any("not_a_real_field" in e and "unknown data field" in e for e in errors), (
        f"expected unknown-field finding, got: {errors}"
    )


def test_validator_anchors_domain_to_root_segment(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Domain check anchors on the first segment under ``root`` — not anywhere in path.parts.

    Regression for the bug where the absolute path happening to contain
    a directory named ``script`` (e.g. checking out the repo under
    ``~/scripts/...``) silently let mis-placed blueprints pass.
    """
    validator = _load_validator()
    # Simulate a checkout living under a directory named "script": the
    # blueprint *declares* domain=automation but lives under .../automation/,
    # which is correct. With the old check, the parent "script" segment
    # would let a script-domain blueprint here pass too — verify the
    # anchor-on-root behaviour rejects that.
    misleading_root = tmp_path / "scripts" / "my-checkout" / "blueprints"
    wrong_dir = misleading_root / "automation" / "pack"
    wrong_dir.mkdir(parents=True)
    bp = wrong_dir / "mis_placed.yaml"
    bp.write_text(
        "blueprint:\n"
        "  name: x\n"
        "  description: x\n"
        "  domain: script\n"  # declared script, but lives under .../automation/...
        "  input: {}\n"
    )
    errors = validator.validate_file(bp, root=misleading_root)
    assert any("blueprint.domain='script'" in e for e in errors), errors

    # And the correctly-placed version passes the directory check.
    right_dir = misleading_root / "script" / "pack"
    right_dir.mkdir(parents=True)
    bp_ok = right_dir / "good.yaml"
    bp_ok.write_text("blueprint:\n  name: x\n  description: x\n  domain: script\n  input: {}\n")
    errors_ok = validator.validate_file(bp_ok, root=misleading_root)
    assert not any("file lives under" in e for e in errors_ok), errors_ok
