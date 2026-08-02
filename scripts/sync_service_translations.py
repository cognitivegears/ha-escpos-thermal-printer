#!/usr/bin/env python3
"""Regenerate the ``services`` translation key in strings.json (and its
translations/en.json mirror) from services.yaml.

services.yaml stays the source of truth for service and field
name/description text (HA renders it even without translations); this
script mirrors that text into strings.json's ``services`` key so it becomes
translatable, without ever hand-editing JSON out of sync with the YAML.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Any

import yaml

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

# See `scripts/sync_manifest_requirements.py` for the invocation-directory
# rationale (dependabot-auto-sync.yml runs scripts from a working directory
# that isn't the script's own location).
ROOT = pathlib.Path.cwd()
COMPONENT = ROOT / "custom_components" / "escpos_printer"
SERVICES_YAML = COMPONENT / "services.yaml"
STRINGS_JSON = COMPONENT / "strings.json"
EN_JSON = COMPONENT / "translations" / "en.json"


def _field_entry(field: dict[str, Any]) -> dict[str, str]:
    """Return the ``{description?, name?}`` translation entry for one field.

    Keys are emitted in the order HA's own translations use (alphabetical:
    "description" before "name"). A field with neither key contributes
    nothing -- never invent text.
    """
    entry: dict[str, str] = {}
    if "description" in field:
        entry["description"] = str(field["description"])
    if "name" in field:
        entry["name"] = str(field["name"])
    return entry


def build_services_section(services_yaml: dict[str, Any]) -> dict[str, Any]:
    """Build the strings.json ``services`` subtree from parsed services.yaml.

    Mapping rules (see task-3-brief.md):
    - service ``name``/``description`` -> ``services.<service>.{name,description}``.
    - top-level fields -> ``services.<service>.fields.<field>``.
    - collapsed section groups (fields carrying their own nested ``fields:``)
      -> the group's own name/description go to
      ``services.<service>.sections.<key>.{name,description}``; its inner
      fields join the same flat ``fields`` namespace as top-level
      fields, since HA keys field translations by field name regardless of
      section (confirmed against installed HA core components, e.g. mqtt).
    """
    services: dict[str, Any] = {}
    for service_key in sorted(services_yaml):
        body = services_yaml[service_key] or {}
        fields: dict[str, dict[str, str]] = {}
        sections: dict[str, dict[str, str]] = {}

        for field_key, field_body in (body.get("fields") or {}).items():
            if not isinstance(field_body, dict):
                continue
            if "fields" in field_body:
                section_entry = _field_entry(field_body)
                if section_entry:
                    sections[field_key] = section_entry
                for inner_key, inner_body in field_body["fields"].items():
                    if not isinstance(inner_body, dict):
                        continue
                    inner_entry = _field_entry(inner_body)
                    if inner_entry:
                        fields[inner_key] = inner_entry
            else:
                field_entry = _field_entry(field_body)
                if field_entry:
                    fields[field_key] = field_entry

        entry: dict[str, Any] = {}
        if "description" in body:
            entry["description"] = str(body["description"])
        if fields:
            entry["fields"] = dict(sorted(fields.items()))
        if "name" in body:
            entry["name"] = str(body["name"])
        if sections:
            entry["sections"] = dict(sorted(sections.items()))

        services[service_key] = entry
    return services


def build_strings_json(services_section: dict[str, Any]) -> dict[str, Any]:
    """Return strings.json's full content with ``services`` regenerated in place."""
    data = json.loads(STRINGS_JSON.read_text(encoding="utf-8"))
    data["services"] = services_section
    return data


def render(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Sync strings.json/translations/en.json 'services' key from services.yaml"
    )
    parser.add_argument(
        "--check", action="store_true", help="Only check for drift; non-zero exit on mismatch"
    )
    args = parser.parse_args()

    services_yaml = yaml.safe_load(SERVICES_YAML.read_text(encoding="utf-8"))
    services_section = build_services_section(services_yaml)
    desired = render(build_strings_json(services_section))

    current_strings = STRINGS_JSON.read_text(encoding="utf-8") if STRINGS_JSON.exists() else ""
    current_en = EN_JSON.read_text(encoding="utf-8") if EN_JSON.exists() else ""

    if args.check:
        problems = []
        if current_strings != desired:
            problems.append("strings.json 'services' is out of sync with services.yaml")
        if current_en != desired:
            problems.append("translations/en.json is out of sync with strings.json")
        if problems:
            for p in problems:
                print(f"❌ {p}")
            return 1
        print("✅ strings.json and translations/en.json are in sync with services.yaml")
        return 0

    changed = False
    if current_strings != desired:
        STRINGS_JSON.write_text(desired, encoding="utf-8")
        changed = True
    if current_en != desired:
        EN_JSON.write_text(desired, encoding="utf-8")
        changed = True

    print(
        "✅ Updated strings.json and translations/en.json" if changed else "✅ Already up-to-date"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
