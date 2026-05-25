#!/usr/bin/env python3
"""Lightweight YAML validity check for the bundled Home Assistant blueprints.

This is a smoke test that catches the most common ways a blueprint
breaks during editing:

- the YAML doesn't parse
- the top-level ``blueprint:`` key is missing
- ``blueprint.name`` / ``blueprint.description`` / ``blueprint.domain``
  / ``blueprint.input`` are missing
- ``blueprint.domain`` is something other than ``automation`` or
  ``script``
- the directory layout does not match the domain
- a ``service: escpos_printer.<name>`` reference points at a service
  that doesn't exist in ``custom_components/escpos_printer/services.yaml``
- a ``data:`` block at a service call uses field names the service's
  schema doesn't declare (typo / drift between blueprints and integration)

It does *not* run HA's full blueprint loader (which would pull in
the whole HA dependency surface for a CI check we want to be cheap).
Full validation happens when the user imports the blueprint into
their Home Assistant instance.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml

_VALID_DOMAINS = frozenset({"automation", "script"})

# HA service-call data field that's always implicit (target → device_id /
# entity_id / area_id). Service-specific schemas don't list these.
_HA_IMPLICIT_DATA_FIELDS = frozenset({"device_id", "entity_id", "area_id"})

# The integration domain for service-call linting.
_INTEGRATION_DOMAIN = "escpos_printer"


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that tolerates HA's ``!input`` (and other custom) tags.

    Inheriting from ``SafeLoader`` keeps the YAML 1.1 safe-construction
    semantics (no arbitrary-object instantiation). The added multi-
    constructor for the ``!`` tag prefix just returns the raw scalar /
    sequence / mapping payload so the validator can keep walking the
    structure. We don't need to *interpret* `!input`, only to *parse*
    around it.
    """


def _ignore_unknown(loader: yaml.Loader, tag_suffix: str, node: yaml.Node) -> Any:
    del tag_suffix
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node)
    return None


_BlueprintLoader.add_multi_constructor("!", _ignore_unknown)


def _load_services_yaml(services_path: Path) -> dict[str, set[str]]:
    """Parse the integration's ``services.yaml`` into ``{service: fields}``.

    Returns an empty dict on any failure (so the service-lint becomes a
    silent no-op rather than a hard failure when run outside the repo
    layout, e.g. on a forked copy of just ``blueprints/``).
    """
    try:
        text = services_path.read_text(encoding="utf-8")
    except OSError:
        return {}
    try:
        # vanilla SafeLoader is fine — services.yaml has no custom tags.
        data: Any = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    if not isinstance(data, dict):
        return {}
    services: dict[str, set[str]] = {}
    for svc, body in data.items():
        if not isinstance(svc, str) or not isinstance(body, dict):
            continue
        fields = body.get("fields", {}) or {}
        if not isinstance(fields, dict):
            services[svc] = set()
            continue
        services[svc] = set(fields.keys())
    return services


def _walk_service_calls(node: Any) -> list[tuple[str, dict[str, Any]]]:
    """Yield ``(service_str, data_block)`` tuples found anywhere in *node*.

    A "service call" is a mapping with a ``service:`` key whose value is
    a string. ``data:`` is the sibling mapping (or empty dict if absent).
    Walks recursively into lists and nested mappings — HA blueprint
    action sequences are arbitrarily nested via ``repeat:``, ``if:``,
    ``choose:``, etc.
    """
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        svc = node.get("service")
        if isinstance(svc, str):
            data = node.get("data") if isinstance(node.get("data"), dict) else {}
            found.append((svc, data))
        for value in node.values():
            found.extend(_walk_service_calls(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_service_calls(item))
    return found


def _lint_service_calls(bp_data: Any, services_index: dict[str, set[str]]) -> list[str]:
    """Return findings for ``escpos_printer.*`` calls that don't match the schema."""
    if not services_index:
        # We couldn't load services.yaml — skip silently rather than failing.
        return []
    findings: list[str] = []
    for svc_str, data in _walk_service_calls(bp_data):
        if "." not in svc_str:
            continue
        domain, _, name = svc_str.partition(".")
        if domain != _INTEGRATION_DOMAIN:
            continue
        if name not in services_index:
            findings.append(
                f"service '{svc_str}' is not declared in services.yaml "
                f"(known: {', '.join(sorted(services_index)) or 'none'})"
            )
            continue
        allowed_fields = services_index[name] | _HA_IMPLICIT_DATA_FIELDS
        for field_name in data:
            if not isinstance(field_name, str):
                continue
            if field_name in allowed_fields:
                continue
            findings.append(
                f"service '{svc_str}' has unknown data field '{field_name}' "
                f"(declared: {', '.join(sorted(services_index[name])) or 'none'})"
            )
    return findings


def _find_services_yaml(blueprint_path: Path) -> Path | None:
    """Walk up from *blueprint_path* to find a sibling integration's
    ``services.yaml``.

    The conventional repo layout is
    ``<repo>/custom_components/escpos_printer/services.yaml`` with
    blueprints under ``<repo>/blueprints/...``. Walk from the blueprint
    upward looking for that path.
    """
    for parent in [blueprint_path.parent, *blueprint_path.parents]:
        candidate = parent / "custom_components" / _INTEGRATION_DOMAIN / "services.yaml"
        if candidate.is_file():
            return candidate
    return None


def validate_file(path: Path, root: Path | None = None) -> list[str]:
    """Return a list of human-readable error messages (empty when ok).

    When ``root`` is supplied, the domain-vs-directory check anchors on
    the first path segment under ``root`` (the HA convention is
    ``<root>/<domain>/<author>/<file>.yaml``). Without a root we fall
    back to walking ``path.parts`` from the right, which still beats
    matching ``"script"`` anywhere in the absolute path (which would
    pass for, e.g., a checkout under ``~/scripts/...``).
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        return [f"could not read: {err}"]
    try:
        # ``_BlueprintLoader`` derives from ``yaml.SafeLoader`` and only
        # *parses* unknown tags — it never instantiates Python objects
        # from YAML. Safe by construction; ruff's S506 and bandit's
        # B506 both flag the literal "yaml.load" without recognising
        # the SafeLoader subclass.
        data: Any = yaml.load(text, Loader=_BlueprintLoader)  # noqa: S506  # nosec B506
    except yaml.YAMLError as err:
        return [f"YAML parse error: {err}"]
    if not isinstance(data, dict):
        return ["top-level must be a mapping"]
    bp = data.get("blueprint")
    if not isinstance(bp, dict):
        return ["missing top-level 'blueprint:' mapping"]
    errors: list[str] = [
        f"blueprint.{required} is missing"
        for required in ("name", "description", "domain", "input")
        if required not in bp
    ]
    domain = bp.get("domain")
    if domain not in _VALID_DOMAINS:
        errors.append(f"blueprint.domain={domain!r} is not one of {sorted(_VALID_DOMAINS)}")
    inputs = bp.get("input")
    if inputs is not None and not isinstance(inputs, dict):
        errors.append("blueprint.input must be a mapping")
    # Directory must match the declared domain so users importing via
    # the GitHub raw URL land in the right HA blueprint pool.
    if domain in _VALID_DOMAINS and _domain_segment(path, root) != domain:
        errors.append(
            f"file lives under {path.parent} but blueprint.domain={domain!r} "
            f"(domain segment should be the first directory under the scan root)"
        )
    # Service-call lint: every `escpos_printer.<name>` reference must
    # resolve to a service declared in the integration's services.yaml,
    # and each `data:` field name must be declared in that service's
    # schema. Skips silently when services.yaml isn't reachable (e.g.
    # the blueprints/ directory exported alone to a fork).
    services_path = _find_services_yaml(path)
    if services_path is not None:
        services_index = _load_services_yaml(services_path)
        # Walk the entire document tree — ``action:`` / ``sequence:`` are
        # top-level siblings of ``blueprint:``, not nested inside it.
        errors.extend(_lint_service_calls(data, services_index))
    return errors


def _domain_segment(path: Path, root: Path | None) -> str | None:
    """Return the path segment that should match ``blueprint.domain``.

    With a ``root`` we anchor on the first segment under it (HA's
    canonical layout: ``<root>/<domain>/<author>/<file>.yaml``). Without
    one we fall back to the third-from-last path segment, which still
    beats matching ``"script"`` *anywhere* in the absolute path (which
    would silently pass for a checkout under, e.g., ``~/scripts/``).
    """
    if root is not None:
        try:
            rel_parts = path.resolve().relative_to(root.resolve()).parts
        except ValueError:
            return None
        return rel_parts[0] if rel_parts else None
    parts = path.parts
    return parts[-3] if len(parts) >= 3 else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "root",
        nargs="?",
        default="blueprints",
        help="Directory to scan (default: blueprints)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    if not root.is_dir():
        print(f"error: {root} is not a directory", file=sys.stderr)
        return 2
    files = sorted(root.rglob("*.yaml"))
    if not files:
        print(f"warning: no .yaml files under {root}", file=sys.stderr)
        return 0
    total = 0
    failed = 0
    for f in files:
        errors = validate_file(f, root=root)
        total += 1
        if errors:
            failed += 1
            print(f"FAIL {f}", file=sys.stderr)
            for e in errors:
                print(f"  - {e}", file=sys.stderr)
        else:
            print(f"  ok {f}")
    print(f"\n{total - failed}/{total} blueprint files pass.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
