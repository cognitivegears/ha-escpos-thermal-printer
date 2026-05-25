"""Render every blueprint's ``variables:`` block through HA's sandboxed
template environment.

The structural YAML validator in ``scripts/validate_blueprints.py`` only
parses the file — it never *renders* the embedded Jinja, so it cannot
catch sandbox-policy violations like ``list.append()``,
``list.extend()``, or ``dict.pop()``. Those only surface when HA's
``TemplateEnvironment`` actually executes the template and Jinja's
sandbox raises ``SecurityError`` (HA wraps it in ``TemplateError``).

This file renders each blueprint's variables blocks in declaration
order against mock inputs and mock service-response shapes. If anyone
re-introduces an unsafe attribute access (or any other rendering bug
in a variables block), the parametrised test fails with the file +
variable name + offending template.

Why scope to ``variables:`` and not every ``data:`` template? Because
the ``.append()`` bug class — and most other sandbox violations — live
in multi-line "build up a list" templates, which only appear in
``variables:`` blocks. Templates embedded inside ``data:`` are
typically single expressions that don't iterate, and many depend on
context that doesn't exist outside an actual HA run (``repeat.item``,
``trigger.to_state``, etc.). Trying to render those would either give
false negatives (we'd have to feed every possible binding) or false
positives (an ``UndefinedError`` is not a sandbox violation). The
``variables:`` scope is the sharp tool for the bug class we actually
hit.
"""

from __future__ import annotations

from pathlib import Path
import types
from typing import Any

from homeassistant.helpers.template import Template
import pytest
import yaml

# Forces the test harness to wire ``custom_components`` into ``sys.path``
# before the autouse ``fake_bluetooth_module`` fixture in ``conftest.py``
# tries to import the printer subpackage.
from custom_components.escpos_printer import const

_ = const  # keep the import live for ruff/mypy

REPO_ROOT = Path(__file__).resolve().parent.parent
BLUEPRINTS_DIR = REPO_ROOT / "blueprints"


# ---- YAML loader that captures !input references ----------------------------


class _InputRef:
    """Sentinel for an unresolved ``!input <name>`` reference."""

    __slots__ = ("name",)

    def __init__(self, name: str) -> None:
        self.name = name

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"_InputRef({self.name!r})"


def _construct_input(loader: yaml.Loader, node: yaml.Node) -> _InputRef:
    if not isinstance(node, yaml.ScalarNode):
        raise yaml.YAMLError(f"!input must be a scalar, got {type(node).__name__}")
    return _InputRef(loader.construct_scalar(node))


class _BlueprintLoader(yaml.SafeLoader):
    """SafeLoader that captures ``!input`` as a sentinel for later resolution."""


_BlueprintLoader.add_constructor("!input", _construct_input)


def _resolve_inputs(obj: Any, inputs: dict[str, Any]) -> Any:
    """Recursively replace ``_InputRef`` sentinels with values from ``inputs``."""
    if isinstance(obj, _InputRef):
        if obj.name not in inputs:
            raise KeyError(f"unresolved !input '{obj.name}' — add it to the test case")
        return inputs[obj.name]
    if isinstance(obj, dict):
        return {k: _resolve_inputs(v, inputs) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_inputs(v, inputs) for v in obj]
    return obj


# ---- step walker -------------------------------------------------------------


def _walk_steps(steps: list[Any]):
    """Yield each step dict, descending into control-flow nesters in order."""
    for step in steps or []:
        if not isinstance(step, dict):
            continue
        yield step
        for nest_key in ("then", "else", "sequence", "default"):
            inner = step.get(nest_key)
            if isinstance(inner, list):
                yield from _walk_steps(inner)
        choose = step.get("choose")
        if isinstance(choose, list):
            for branch in choose:
                if isinstance(branch, dict):
                    yield from _walk_steps(branch.get("sequence") or [])
        repeat = step.get("repeat")
        if isinstance(repeat, dict):
            yield from _walk_steps(repeat.get("sequence") or [])


def _iter_variables_blocks(blueprint: dict[str, Any]):
    """Yield each ``variables:`` mapping in declaration order."""
    top = blueprint.get("variables")
    if isinstance(top, dict):
        yield top
    for key in ("sequence", "action"):
        steps = blueprint.get(key)
        if isinstance(steps, list):
            for step in _walk_steps(steps):
                vars_block = step.get("variables")
                if isinstance(vars_block, dict):
                    yield vars_block


# ---- mock service-response shapes (chosen so for-loops actually iterate) -----

_TODO_RESPONSE = {
    "todo.test": {
        "items": [
            {"summary": "Buy milk", "status": "needs_action"},
            {"summary": "Pay bill", "status": "completed"},
        ]
    }
}
_FORECAST_RESPONSE = {
    "weather.test": {
        "forecast": [
            {
                "datetime": "2026-05-24T12:00:00+00:00",
                "temperature": 75,
                "templow": 60,
                "condition": "sunny",
            },
            {
                "datetime": "2026-05-25T12:00:00+00:00",
                "temperature": 70,
                "templow": 55,
                "condition": "partlycloudy",
            },
        ]
    }
}
_CAL_RESPONSE = {
    "calendar.test": {
        "events": [
            {"start": "2026-05-24T10:00:00+00:00", "summary": "Standup"},
            {"start": "2026-05-24T13:00:00+00:00", "summary": "Project review"},
        ]
    }
}


def _trigger_namespace(prior_items: list[dict[str, str]]):
    """Build a mock ``trigger`` object with the fields HA exposes during state triggers."""
    return types.SimpleNamespace(
        from_state=types.SimpleNamespace(attributes={"items": prior_items}),
        to_state=types.SimpleNamespace(attributes={"items": []}),
    )


# Per-blueprint test cases. Each entry supplies values for every `!input`
# referenced by the file, plus mock context variables for any
# ``response_variable`` the script consumes and any ``trigger`` it reads.
# Inputs are deliberately set to make for-loops iterate (so unsafe ops in
# the loop body actually execute and trip the sandbox).
BLUEPRINT_CASES: dict[str, dict[str, Any]] = {
    "blueprints/script/escpos_printer/todo_list.yaml": {
        "inputs": {
            "todo_entity": "todo.test",
            "printer": "device_id",
            "include_completed": True,
            "numbered": True,
            "title": "My TODO",
            "style": "double",
        },
        "context": {"todo_response": _TODO_RESPONSE},
    },
    "blueprints/script/escpos_printer/shopping_list.yaml": {
        "inputs": {
            "todo_entity": "todo.test",
            "printer": "device_id",
            "title": "Shopping",
            "style": "double",
        },
        "context": {"todo_response": _TODO_RESPONSE},
    },
    "blueprints/script/escpos_printer/recipe_card.yaml": {
        "inputs": {
            "printer": "device_id",
            "name": "Test Recipe",
            "servings": "4",
            "ingredients": "Flour\nSugar\nButter",
            "steps": "Mix\nBake\nServe",
            "style": "double",
        },
        "context": {},
    },
    "blueprints/script/escpos_printer/weather_forecast.yaml": {
        "inputs": {
            "printer": "device_id",
            "weather_entity": "weather.test",
            "title": "Forecast",
            "days": 3,
            "max_condition_length": 8,
        },
        "context": {"forecast_response": _FORECAST_RESPONSE},
    },
    "blueprints/script/escpos_printer/receipt.yaml": {
        "inputs": {
            "printer": "device_id",
            "title": "Receipt",
            "items": [
                {"name": "Coffee", "price": 3.5},
                {"name": "Bagel", "price": 2.25},
            ],
            "tax_rate": 8.875,
            "currency": "$",
        },
        "context": {},
    },
    "blueprints/automation/escpos_printer/daily_agenda.yaml": {
        "inputs": {
            "calendar_entity": "calendar.test",
            "printer": "device_id",
            "print_time": "07:00:00",
            "lookahead_hours": 24,
            "style": "double",
            "max_title_length": 40,
        },
        "context": {"cal_response": _CAL_RESPONSE},
    },
    "blueprints/automation/escpos_printer/sensor_alert.yaml": {
        "inputs": {
            "printer": "device_id",
            "sensor": "binary_sensor.test",
            "target_state": "on",
            "alert_title": "ALERT",
            "style": "double",
        },
        "context": {},
    },
    "blueprints/automation/escpos_printer/todo_item.yaml": {
        "inputs": {
            "printer": "device_id",
            "todo_entity": "todo.test",
            "box_style": "double",
            "max_items_per_trigger": 5,
            "cut_per_item": True,
        },
        "context": {"trigger": _trigger_namespace([{"summary": "old"}])},
    },
}


def _load_blueprint(rel_path: str, inputs: dict[str, Any]) -> dict[str, Any]:
    text = (REPO_ROOT / rel_path).read_text(encoding="utf-8")
    raw = yaml.load(text, Loader=_BlueprintLoader)  # noqa: S506  # nosec B506
    assert isinstance(raw, dict), f"{rel_path}: top-level must be a mapping"
    return _resolve_inputs(raw, inputs)


def _render_variables_block(
    block: dict[str, Any],
    hass: Any,
    context: dict[str, Any],
) -> None:
    """Render each value in declaration order, accumulating into ``context``.

    Mutates ``context`` so later blocks (and later keys within the same
    block) see previously-rendered values. String values containing
    Jinja markers are passed through ``Template.async_render``; everything
    else is stored as-is.
    """
    for key, value in block.items():
        if isinstance(value, str) and ("{{" in value or "{%" in value):
            tmpl = Template(value, hass)
            context[key] = tmpl.async_render(variables=context, parse_result=True)
        else:
            context[key] = value


@pytest.mark.parametrize("rel_path", sorted(BLUEPRINT_CASES.keys()))
async def test_blueprint_variables_render_in_sandbox(
    hass: Any,  # provided by pytest-homeassistant-custom-component
    rel_path: str,
) -> None:
    """Every ``variables:`` block in every blueprint renders without sandbox violations."""
    case = BLUEPRINT_CASES[rel_path]
    blueprint = _load_blueprint(rel_path, case["inputs"])
    context: dict[str, Any] = dict(case["context"])

    blocks = list(_iter_variables_blocks(blueprint))
    assert blocks, f"{rel_path}: no variables: blocks found — did the layout change?"

    for block in blocks:
        try:
            _render_variables_block(block, hass, context)
        except Exception as err:
            pytest.fail(
                f"{rel_path}: failed to render variables block {list(block)!r}: "
                f"{type(err).__name__}: {err}"
            )


def test_blueprint_cases_cover_every_blueprint() -> None:
    """Guard: every blueprint under blueprints/ must have a registered test case.

    Without this, someone adding a new blueprint could ship a sandbox
    violation simply by forgetting to add an entry to ``BLUEPRINT_CASES``
    — the parametrised test would silently not cover the new file.
    """
    on_disk = {
        str(p.relative_to(REPO_ROOT))
        for p in sorted(BLUEPRINTS_DIR.rglob("*.yaml"))
    }
    registered = set(BLUEPRINT_CASES.keys())
    missing = on_disk - registered
    extra = registered - on_disk
    assert not missing, (
        f"blueprints without a template-safety test case: {sorted(missing)} "
        f"— add them to BLUEPRINT_CASES in this file"
    )
    assert not extra, (
        f"BLUEPRINT_CASES references missing files: {sorted(extra)}"
    )


# ---- self-test: the harness must actually catch a regression -----------------


async def test_harness_catches_unsafe_append(hass: Any, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    """Regression-proof: confirm the harness *fails* when given an unsafe template.

    If someone "simplifies" the test in a way that stops exercising HA's
    sandbox, this canary fires.
    """
    unsafe_block = {
        "rows": (
            "{% set out = [] %}"
            "{% for i in [1, 2, 3] %}"
            "  {% set _ = out.append([i]) %}"
            "{% endfor %}"
            "{{ out }}"
        )
    }
    with pytest.raises(Exception) as excinfo:
        _render_variables_block(unsafe_block, hass, {})
    msg = str(excinfo.value).lower()
    assert "unsafe" in msg or "append" in msg or "security" in msg, (
        f"expected sandbox error but got: {excinfo.value!r}"
    )


async def test_harness_passes_safe_namespace_pattern(hass: Any) -> None:  # type: ignore[no-untyped-def]
    """Counter-canary: the namespace pattern we use in the fix must render cleanly."""
    safe_block = {
        "rows": (
            "{% set ns = namespace(out=[]) %}"
            "{% for i in [1, 2, 3] %}"
            "  {% set ns.out = ns.out + [[i]] %}"
            "{% endfor %}"
            "{{ ns.out }}"
        )
    }
    ctx: dict[str, Any] = {}
    _render_variables_block(safe_block, hass, ctx)
    assert ctx["rows"] == [[1], [2], [3]]
