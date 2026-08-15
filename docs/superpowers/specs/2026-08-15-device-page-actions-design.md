# Device page actions: buttons + repairs-based calibration entry

**Date:** 2026-08-15
**Status:** Approved (design), pending implementation
**Problem:** The device page shows nothing actionable (only sensors and the
notify entity), and the calibration wizard is buried behind Settings →
Devices & services → integration entry → Configure → "calibrate" — users
don't find it. HA offers no way to launch an interactive flow from a device
page, so the wizard needs a sanctioned, visible entry point elsewhere, and
the device page needs a Controls card.

## Part 1: Button platform

New `custom_components/escpos_printer/button.py` with four `ButtonEntity`
subclasses per config entry, attached to the printer device via the existing
`build_device_info()`:

| Button | Action |
|---|---|
| Feed | `adapter.feed(lines=3)` — fixed tear-off advance; there is no entry-level feed default to honor |
| Cut | `adapter.cut(mode=<entry's CONF_DEFAULT_CUT, falling back to "full" when that is "none">)` — a Cut button must always cut |
| Beep | `adapter.beep()` (adapter defaults: 2 beeps × 4 units) |
| Sample test print | Composed sample receipt (below) |

- Add `"button"` to `PLATFORMS` in `__init__.py`; entity names in
  `strings.json` (+ regenerated `translations/en.json`), icons in
  `icons.json`.
- Presses run the existing adapter methods
  (`printer/control_operations.py`) on executor threads under the same
  per-adapter `asyncio.Lock` the services use. No new I/O paths.
- Beep on a buzzerless printer behaves exactly like today's `beep`
  service — no special-casing.
- No calibration-sheet button (deliberate: the repairs entry covers
  calibration; `calibration_print` service remains for power users).

### Sample test print

One small shared function (module: `services/` or `printer/` — implementer's
choice, wherever the box/table layout helpers `_render_box_layout` /
`_render_table_layout` are importable without cycles) composing one
uninterrupted receipt:

1. Integration logo `brand/logo.png` (666×256 RGBA) through the standard
   image dither pipeline
2. Boxed header: "ESC/POS Sample Print" + printer name (box renderer)
3. Styled text lines demonstrating bold / underline / double-size
4. Small two-column table (table renderer)
5. Separator rule, then a QR code linking to the project repo
6. Feed + cut per the entry's configured defaults

Button-only for now; the shared function makes a future `print_sample`
service trivial, but that service is explicitly out of scope (YAGNI).

## Part 2: Repairs-based calibration entry

- New `custom_components/escpos_printer/repairs.py` implementing
  `async_create_fix_flow`, returning a flow class built as
  `RepairsFlow + CalibrationFlowMixin` — the real wizard, unchanged,
  running from Settings → Repairs. `CalibrationFlowMixin`
  (`_config_flow/calibration_steps.py`) is already flow-agnostic (needs
  only `hass` + `config_entry`); the repairs flow supplies the
  `config_entry` from issue data (entry_id).
- **Trigger:** `async_setup_entry` raises one fixable issue per never-
  calibrated entry — "never calibrated" = none of the `_CALIB_TO_CONF`
  option keys (`CONF_IMPL`, `CONF_WIDTH_PIXELS`, `CONF_LINE_WIDTH`,
  `CONF_CODEPAGE`) present in `entry.options`. The check runs on every
  setup/reload: condition gone → issue deleted (the wizard's save path
  already schedules a reload, so completing it self-clears the issue).
- Issue: `is_fixable=True`, severity `warning` (mildest available),
  `issue_id` keyed by entry_id, deleted in `async_unload_entry` only on
  entry removal (not on reload).
- HA's built-in "Ignore" provides permanent dismissal; we never re-raise
  an ignored issue (issue registry handles this).

### Copy (approved wording — optional, not width-only)

- Title: **"Printer not yet calibrated"**
- Description: "The optional calibration tool prints test pages to tune
  print width and character set for this printer and paper. Run it now,
  or ignore this — printing works without it."
- The fix flow opens on the wizard's existing confirm step; no
  obligation-implying copy anywhere.

## Testing

- **Buttons:** each press calls the right adapter method (Feed → 3 lines;
  Cut → entry default with "none"→"full" fallback; Beep → adapter
  defaults); entities registered on the correct device; sample
  print issues image + text + QR calls in order within a single adapter
  session.
- **Repairs:** uncalibrated entry → issue exists after setup; entry with
  any `_CALIB_TO_CONF` key in options → no issue; completing the fix flow
  → options saved, entry reloaded, issue gone. Reuse existing
  calibration-flow test fixtures.

## Docs / changelog

- CHANGELOG `[Unreleased]` → Added: device page buttons (Feed, Cut, Beep,
  Sample test print); Added: repairs suggestion for uncalibrated printers.
- Calibration docs: mention the Repairs entry point alongside Configure.
- README one-liner; ROADMAP item 1 trimmed (buttons shipped; calibration-
  sheet button noted as not planned).

## Out of scope

- `print_sample` service (function is shared; service can come later).
- Cash-drawer button (ROADMAP item 2).
- Any change to the options-flow menu structure.
- `configuration_url` deep-linking (rejected: conflicts with the
  printer's own web UI and "Visit device" semantics).

## Branch

New branch based on `main` after PR #151 (target picker / 1.2.0) merges —
the repairs check and buttons are independent of the target work, but
CHANGELOG placement assumes 1.2.0 is cut.
