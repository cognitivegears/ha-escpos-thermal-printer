#!/usr/bin/env python3
"""Verify manifest.json and pyproject.toml carry the same version string.

HACS uses ``manifest.json::version`` to surface releases to users. The
``pyproject.toml`` version is what build systems and developer tools see.
Drift between the two means HACS users see a different version than what
the codebase advertises, so we treat divergence as a CI failure.
"""

from __future__ import annotations

import json
import pathlib
import sys

try:
    import tomllib  # Python 3.11+
except Exception as exc:  # pragma: no cover
    raise SystemExit("Python 3.11+ required for tomllib") from exc

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "escpos_printer" / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"


def main() -> int:
    manifest_version = json.loads(MANIFEST.read_text())["version"]
    pyproject_version = tomllib.loads(PYPROJECT.read_text())["project"]["version"]
    if manifest_version == pyproject_version:
        print(f"OK manifest.json and pyproject.toml both at {manifest_version}")
        return 0
    print(
        "ERROR Version drift detected:\n"
        f"  manifest.json   = {manifest_version}\n"
        f"  pyproject.toml  = {pyproject_version}\n"
        "Update both to the same value before merging.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
