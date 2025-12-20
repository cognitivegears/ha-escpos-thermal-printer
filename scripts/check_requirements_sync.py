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

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    print("Python 3.11+ required for tomllib", file=sys.stderr)
    sys.exit(1)

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet

ROOT = pathlib.Path(__file__).resolve().parents[1]


def parse_pyproject() -> dict[str, SpecifierSet]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    deps = data.get("project", {}).get("dependencies", [])
    result: dict[str, SpecifierSet] = {}
    for dep in deps:
        r = Requirement(dep)
        result[r.name.lower()] = r.specifier
    return result


def parse_manifest() -> dict[str, SpecifierSet]:
    data = json.loads((ROOT / "custom_components" / "escpos_printer" / "manifest.json").read_text())
    reqs = data.get("requirements", [])
    result: dict[str, SpecifierSet] = {}
    for dep in reqs:
        r = Requirement(dep)
        result[r.name.lower()] = r.specifier
    return result


def compatible(spec_py: SpecifierSet, spec_mani: SpecifierSet) -> bool:
    """Return True if pyproject spec is within manifest spec (or equal)."""
    # Heuristic: check a small probe set for intersection and containment.
    probes = [
        "0.0.0",
        "7.4.2",
        "10.0.0",
        "11.0.0",
        "11.3.0",
        "0.16.1",
        "3.1",
    ]
    # If either is empty, treat as wildcard
    if not str(spec_py):
        return True
    if not str(spec_mani):
        return True
    # Any version allowed by pyproject but not allowed by manifest => incompatible
    for v in probes:
        if v in spec_py and v not in spec_mani:
            return False
    return True


def main() -> int:
    py = parse_pyproject()
    mf = parse_manifest()

    missing = set(py.keys()) ^ set(mf.keys())
    if missing:
        print(f"❌ Package sets differ between pyproject and manifest: {sorted(missing)}", file=sys.stderr)
        return 1

    problems = []
    for name in sorted(py.keys()):
        if not compatible(py[name], mf[name]):
            problems.append((name, str(py[name]), str(mf[name])))

    if problems:
        print("❌ Version specifiers incompatible:", file=sys.stderr)
        for name, p, m in problems:
            print(f"  - {name}: pyproject='{p}' vs manifest='{m}'", file=sys.stderr)
        return 1

    print("✅ Requirements in sync: manifest.json and pyproject.toml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

