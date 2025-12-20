#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import pathlib

try:
    import tomllib  # Python 3.11+
except Exception:  # pragma: no cover
    raise SystemExit("Python 3.11+ required for tomllib")

from packaging.requirements import Requirement

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "custom_components" / "escpos_printer" / "manifest.json"
PYPROJECT = ROOT / "pyproject.toml"
UVLOCK = ROOT / "uv.lock"

# Packages for which we intentionally keep a version range in the HA manifest
# to avoid conflicts with Home Assistant's own pins.
MANIFEST_OVERRIDES: dict[str, str] = {
    # Allow HA to satisfy its own Pillow pin (e.g., 11.3.x) while keeping
    # compatibility with our integration.
    "pillow": ">=11.0.0,<12.0.0",
}


def parse_pyproject_dependencies() -> list[Requirement]:
    data = tomllib.loads(PYPROJECT.read_text())
    deps = data.get("project", {}).get("dependencies", [])
    return [Requirement(d) for d in deps]


def parse_uv_lock_versions() -> dict[str, str]:
    if not UVLOCK.exists():
        return {}
    text = UVLOCK.read_text()
    # Naive parser for [[package]] sections to extract top-level pinned versions
    versions: dict[str, str] = {}
    current: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if line == "[[package]]":
            current = {}
            continue
        if line.startswith("name = "):
            current["name"] = line.split("=", 1)[1].strip().strip('"')
            continue
        if line.startswith("version = "):
            current["version"] = line.split("=", 1)[1].strip().strip('"')
            # When we see version, we can store if name present
            if "name" in current:
                versions[current["name"].lower()] = current["version"]
            continue
    return versions


def build_manifest_requirements() -> list[str]:
    reqs = parse_pyproject_dependencies()
    locked = parse_uv_lock_versions()
    out: list[str] = []
    for r in reqs:
        name = r.name
        lower = name.lower()
        # Apply explicit overrides first
        if lower in MANIFEST_OVERRIDES:
            out.append(f"{name}{MANIFEST_OVERRIDES[lower]}")
            continue
        # Prefer exact version from pyproject if present
        version = None
        if r.specifier and "==" in str(r.specifier):
            # Find exact equality
            for spec in str(r.specifier).split(","):
                spec = spec.strip()
                if spec.startswith("=="):
                    version = spec[2:]
                    break
        # Fallback to uv.lock resolved version
        if not version:
            version = locked.get(name.lower())
        if not version:
            raise SystemExit(f"Cannot determine exact version for {name}. Pin it in pyproject or lock with uv.")
        out.append(f"{name}=={version}")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync manifest requirements with pinned versions")
    parser.add_argument("--check", action="store_true", help="Only check for drift; non-zero exit on mismatch")
    args = parser.parse_args()

    desired = build_manifest_requirements()
    manifest = json.loads(MANIFEST.read_text())
    current = manifest.get("requirements", [])

    if args.check:
        # In check mode, treat overrides as valid and allow ranges that are
        # compatible with the pinned pyproject/lock versions.
        desired_set = {Requirement(r).name.lower(): Requirement(r) for r in desired}
        current_set = {Requirement(r).name.lower(): Requirement(r) for r in current}

        problems: list[str] = []
        # Ensure the same package keys exist
        if set(desired_set.keys()) != set(current_set.keys()):
            missing = sorted(set(desired_set.keys()) ^ set(current_set.keys()))
            problems.append(f"Package set mismatch: {missing}")
        else:
            for k in sorted(desired_set.keys()):
                want = desired_set[k].specifier
                have = current_set[k].specifier
                # If desired has exact '==' pins, they must be allowed by current
                eqs = [s.strip()[2:] for s in str(want).split(',') if s.strip().startswith('==')]
                if eqs:
                    for v in eqs:
                        if v not in have:
                            problems.append(f"{k}: manifest does not allow pinned version {v}")
                # Otherwise, accept any range in current

        if problems:
            print("❌ manifest.json requirements do not match pyproject/uv.lock:")
            print("Current:")
            for r in current:
                print(f"  - {r}")
            print("Desired:")
            for r in desired:
                print(f"  - {r}")
            for p in problems:
                print(f"Reason: {p}")
            return 1
        print("✅ manifest.json requirements are compatible with pyproject/uv.lock")
        return 0

    # Auto-fix mode: write the computed desired requirements
    if current != desired:
        manifest["requirements"] = desired
        MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
        print("✅ Updated manifest.json requirements")
    else:
        print("✅ manifest.json requirements are up-to-date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
