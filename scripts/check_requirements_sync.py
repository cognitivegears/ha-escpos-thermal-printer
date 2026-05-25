#!/usr/bin/env python3
"""
Verify that Home Assistant manifest requirements and pyproject dependencies are aligned.

Rules:
- Same top-level packages must appear in both.
- Version specifiers must be compatible (pyproject range ⊆ manifest range), or equal.

This is a simple, pragmatic check. It aims to catch drift, not solve dependency resolution.
"""

from __future__ import annotations

import json
import pathlib
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    print("Python 3.11+ required for tomllib", file=sys.stderr)
    sys.exit(1)

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.version import InvalidVersion, Version

# See `scripts/sync_manifest_requirements.py` for the rationale: anchor
# to the *invocation directory* so `dependabot-auto-sync.yml` (which
# runs this script from `working-directory: pr` against a script copy
# under `base/`) reads the PR head's files, not main's.
ROOT = pathlib.Path.cwd()

# Packages allowed to use non-`==` specifiers in pyproject.toml.
# Mirror the rationale in CLAUDE.md and
# `scripts/sync_manifest_requirements.py` MANIFEST_OVERRIDES.
ALLOWED_NON_PINNED: set[str] = set()


def parse_pyproject() -> dict[str, SpecifierSet]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = data.get("project", {}).get("dependencies", [])
    result: dict[str, SpecifierSet] = {}
    for dep in deps:
        r = Requirement(dep)
        result[r.name.lower()] = r.specifier
    return result


def check_pinned_shape(specs: dict[str, SpecifierSet]) -> list[str]:
    """Return a list of error messages for non-``==``-pinned pyproject deps.

    CLAUDE.md "Dependency Management" mandates `==` for runtime deps so
    builds are reproducible and so a silent transitive bump can't change
    behavior between dev/CI/prod. Packages explicitly allow-listed in
    ``ALLOWED_NON_PINNED`` are exempt.
    """
    problems: list[str] = []
    for name, spec in sorted(specs.items()):
        if name in ALLOWED_NON_PINNED:
            continue
        spec_str = str(spec)
        if not spec_str:
            problems.append(f"{name}: no version specifier (must be ==X.Y.Z)")
            continue
        # Accept either a single `==X.Y.Z` or a single `==`-anchored clause.
        if not all(clause.strip().startswith("==") for clause in spec_str.split(",")):
            problems.append(f"{name}: specifier '{spec_str}' is not pinned with `==`")
    return problems


def parse_manifest() -> dict[str, SpecifierSet]:
    data = json.loads((ROOT / "custom_components" / "escpos_printer" / "manifest.json").read_text())
    reqs = data.get("requirements", [])
    result: dict[str, SpecifierSet] = {}
    for dep in reqs:
        r = Requirement(dep)
        result[r.name.lower()] = r.specifier
    return result


def _pinned_versions(spec: SpecifierSet) -> list[Version]:
    """Return the list of exact versions a spec pins via ``==`` clauses.

    ``check_pinned_shape()`` guarantees pyproject specs reach this
    function as one or more ``==`` clauses, so we can iterate them and
    treat each as an exact version. Returning an empty list signals
    ``ALLOWED_NON_PINNED`` (or a future range allowance) — those skip
    the check.
    """
    out: list[Version] = []
    for clause in str(spec).split(","):
        s = clause.strip()
        if not s.startswith("=="):
            continue
        raw = s[2:].lstrip("=")
        try:
            out.append(Version(raw))
        except InvalidVersion:
            continue
    return out


def compatible(spec_py: SpecifierSet, spec_mani: SpecifierSet) -> bool:
    """Return True if pyproject's pinned version satisfies the manifest spec.

    pyproject deps are guaranteed ``==``-pinned by
    :func:`check_pinned_shape`, so the question reduces to "does the
    pinned version sit inside the manifest's spec?" — a direct
    membership check that doesn't rely on a hand-maintained probe set.
    Empty manifest specs (wildcards) and pyproject specs we couldn't
    pin (e.g. future ``ALLOWED_NON_PINNED`` entries) are treated as
    compatible since this check is about catching drift, not enforcing
    pin shape (that's :func:`check_pinned_shape`'s job).
    """
    if not str(spec_mani):
        return True
    pins = _pinned_versions(spec_py)
    if not pins:
        return True
    return all(p in spec_mani for p in pins)


def main() -> int:
    py = parse_pyproject()
    mf = parse_manifest()

    missing = set(py.keys()) ^ set(mf.keys())
    if missing:
        print(
            f"❌ Package sets differ between pyproject and manifest: {sorted(missing)}",
            file=sys.stderr,
        )
        return 1

    shape_problems = check_pinned_shape(py)
    if shape_problems:
        print("❌ pyproject.toml dependencies must be pinned with `==`:", file=sys.stderr)
        for msg in shape_problems:
            print(f"  - {msg}", file=sys.stderr)
        return 1

    problems = [
        (name, str(py[name]), str(mf[name]))
        for name in sorted(py.keys())
        if not compatible(py[name], mf[name])
    ]

    if problems:
        print("❌ Version specifiers incompatible:", file=sys.stderr)
        for name, p, m in problems:
            print(f"  - {name}: pyproject='{p}' vs manifest='{m}'", file=sys.stderr)
        return 1

    print("✅ Requirements in sync: manifest.json and pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
