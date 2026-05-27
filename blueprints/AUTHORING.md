# Authoring Blueprints

This guide covers writing your own ESC/POS blueprint — for your own HA install or as a contribution back to this repo. The catalogue and per-blueprint notes live in [`blueprints/README.md`](README.md).

A blueprint is a single YAML file with a `blueprint:` metadata block plus the normal HA action shape — `trigger:` + `action:` for automations, `sequence:` for scripts. The `blueprint.input:` block declares what the user fills in when they create a script/automation from your blueprint.

## Workflow for your own HA install

1. **Copy an existing blueprint** as a starting template. Pick the one closest to your use case:

   | I want… | Start from |
   |---|---|
   | A state-trigger automation (sensor changes → print) | `automation/escpos_printer/sensor_alert.yaml` |
   | A time-trigger automation (fires at a fixed time) | `automation/escpos_printer/daily_agenda.yaml` |
   | A script with user-supplied form fields | `script/escpos_printer/receipt.yaml` |
   | A todo-diff (print on new items) | `automation/escpos_printer/todo_item.yaml` |
   | Camera snapshot on trigger | `automation/escpos_printer/doorbell_snapshot.yaml` |
   | A QR code script | `script/escpos_printer/guest_wifi_qr.yaml` |

2. **Drop the YAML** into `<config>/blueprints/<script|automation>/<your-author-slug>/<name>.yaml`.

3. **Reload** via **Settings → Automations & Scenes → Blueprints** (no HA restart needed).

4. **Create a script/automation from it** in the UI, fill in the inputs, save, run. Iterate by editing the file and reloading.

## Key concepts (the things that took the longest to internalise)

- **`!input foo`** is a YAML-level substitution at script-instantiation time. HA splices the input's literal value into the YAML at every `!input foo` site. Combine this with Jinja in the input value (e.g. a user-supplied template typed into a text field) and HA renders at run time with the action's local variable scope. See `morning_briefing.yaml`'s `footer:` input for the canonical example.
- **`mode:` is a top-level key**, sibling of `blueprint:` — not nested inside it. Use `mode: single` for time triggers (drops re-fires while a previous fire is still running); `mode: queued` + `max_exceeded: silent` for state triggers (avoids log spam on bulk state changes).
- **`selector:` defines the UI control.** `text: {}` is a free-form field, `boolean: {}` is a switch, `entity: {domain: todo}` is an entity picker filtered by domain, `device: {integration: escpos_printer}` is a device picker, `number: {min: 1, max: 16, step: 1}` is a number input, `select: {options: [a, b, c]}` is a dropdown.
- **Service `data:` fields are Jinja-rendered at call time.** Inside a templated value you can reference `trigger.to_state`, `repeat.item`, and any HA state (`states('sensor.foo')`).

## Minimal shapes

A complete minimal script blueprint:

```yaml
blueprint:
  name: My Script
  description: One-line summary.
  domain: script
  input:
    text:
      name: Text to print
      selector:
        text: {}
mode: queued
max_exceeded: silent
sequence:
  - service: escpos_printer.print_text_utf8
    data:
      text: !input text
  - service: escpos_printer.cut
```

A complete minimal automation blueprint:

```yaml
blueprint:
  name: My Automation
  description: One-line summary.
  domain: automation
  input:
    sensor:
      name: Sensor to watch
      selector:
        entity: {}
mode: queued
max_exceeded: silent
trigger:
  - platform: state
    entity_id: !input sensor
action:
  - service: escpos_printer.print_text_utf8
    data:
      text: "{{ trigger.to_state.name }} is now {{ trigger.to_state.state }}"
  - service: escpos_printer.cut
```

## Validating your blueprint

Three levels of validation, from lightest to strictest. Use whichever ones match how committed you are to shipping the blueprint to other people.

**Level 1 — Home Assistant itself, on import.** The cheapest check: drop the YAML into `<config>/blueprints/<domain>/<author>/<name>.yaml` and reload **Settings → Automations & Scenes → Blueprints**. If the YAML fails to parse or required keys are missing, HA shows the error in the blueprints list. If a *service* reference is wrong, that error only surfaces when you create a script/automation from the blueprint and run it. Fastest feedback loop for iterating; weakest at catching service-name typos.

**Level 2 — generic YAML syntax check.** If you don't have this repo cloned, run a vanilla YAML lint that understands HA's `!input` tag. The simplest path is `yamllint` via [`uvx`](https://github.com/astral-sh/uv):

```sh
uvx yamllint -d '{extends: default, rules: {line-length: disable, document-start: disable}}' my-blueprint.yaml
```

Catches: parse errors, indentation issues, duplicate keys. Doesn't catch: missing required `blueprint.*` fields, service-name typos, field-name drift.

**Level 3 — this repo's `validate_blueprints.py`.** If you've cloned `ha-escpos-thermal-printer`, the bundled validator is much stricter than YAML lint alone:

```sh
uv run python scripts/validate_blueprints.py path/to/your/blueprints/
```

Checks: YAML parse, required `blueprint.name` / `.description` / `.domain` / `.input` fields, `blueprint.domain` matches the directory layout, **every `service: escpos_printer.<name>` reference resolves against `services.yaml`**, and **every `data:` field name matches the service's voluptuous schema**. The service-call lint is the one Level 1 / Level 2 can't replicate — it catches typos like `print_text_utf` (missing `8`) and `data: { not_a_real_field: ... }` before a user ever hits run.

If your blueprint ships alongside markdown docs containing fenced bash, also run:

```sh
uv run python scripts/extract_markdown_bash.py path/to/your/blueprints/
```

Walks `*.md` under the path, extracts ```` ```bash ```` blocks, runs `shellcheck` against them, and smoke-execs any block that contains the password-generator pipeline 10× to catch SIGPIPE-class regressions.

For the unit-test equivalent (useful in your own CI):

```sh
uv run pytest tests/test_blueprints_yaml.py tests/test_markdown_bash.py -q
```

Pre-commit hooks in this repo run all three on every commit touching `blueprints/`. If you fork the repo, install pre-commit with `uvx pre-commit install` and the same gates run on your local commits.

## Sharing publicly

Push the YAML to a GitHub repo and share the **raw URL**. Others import via HA's **Import Blueprint** dialog (paste raw URL). For the one-click badge format used in the [README catalogue](README.md#available-blueprints), generate the URL-encoded path via [`my.home-assistant.io`](https://my.home-assistant.io/) and wrap it in the standard badge `![…](…)` markup.

## Contributing back to this repo

In addition to all of the above:

- **File location must match `blueprint.domain`.** Scripts go under `blueprints/script/<author>/...`; automations under `blueprints/automation/<author>/...`. `scripts/validate_blueprints.py` catches drift.
- **Service references are linted** against `custom_components/escpos_printer/services.yaml` — a typo like `print_text_utf` (missing `8`) fails the validator. Field names in each `data:` block are likewise checked.
- **Use `print_text_utf8`, not `print_text`**, for any user-supplied text. `print_text_utf8` transcodes UTF-8 to the printer's codepage; `print_text` ships bytes raw (use it only for known-ASCII labels like "Notes" or "Total").
- **Sanitise text that lands in a layout cell** (`print_table`, `print_kvtable`) with the canonical chain `.replace('\n', ' ').replace('\r', ' ').replace('|', '/').replace('\t', ' ') | trim`. See `morning_briefing.yaml` for the canonical use.
- **Default `style: auto`** for borders — the integration auto-picks the right glyph family per printer codepage. Don't hardcode `single` or `double` without a reason.
- **Avoid `print_text_image`** unless you need glyphs the printer's hardware codepage can't render (CJK, emoji, fancy fonts). Image commands aren't supported on every ESC/POS printer.
- **Validate locally** before pushing using the Level 3 commands documented under "Validating your blueprint" above. The same gates run via pre-commit (`uvx pre-commit install`) and in CI.
- **Add three things** in the same PR: a row in the "Available blueprints" table in `README.md` with an import badge, a `### Your Blueprint Name` block under "Per-blueprint notes", and a bullet under `## [Unreleased]` `### Added` in `CHANGELOG.md`.

## Modifying an existing blueprint (fork or in-place)

Two options:

1. **Fork this repo**, edit the YAML, and import via the raw URL of your fork.
2. **Copy the YAML** straight into `<config>/blueprints/<domain>/<author>/<file>.yaml` on your HA host and edit in place. HA picks up the changes on the next blueprints-page reload.

## Resources

- [Home Assistant's official blueprint tutorial](https://www.home-assistant.io/docs/blueprint/tutorial/) — definitive reference for the YAML schema and selector types.
- [The 13 existing blueprints in this directory](.) — every common shape (state trigger, time trigger, todo-diff, image, QR, multi-column table, multi-section conditional) is represented. Pick the closest match and tweak.
- [`CLAUDE.md`](../CLAUDE.md) — repo conventions for service usage, sanitiser patterns, text-mode vs image-mode tradeoffs, and the validator / extractor / markdown-lint pipeline.
