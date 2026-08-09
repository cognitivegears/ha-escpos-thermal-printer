# Printer calibration wizard — design

**Date:** 2026-08-09
**Status:** approved design, pending implementation plan
**Ships in:** 1.1.0 (unreleased; folds into the existing changelog section)

## Problem

A user whose printer isn't in the profile database (or its dropdown aliases) lands
on "Generic (no profile)" and has to discover four settings by trial and error:
image implementation (garbled letters when wrong), pixel width (stretched or
half-width images), line width (wrapped or short text), and codepage (mangled
accents). Each has a per-entry option already; nothing guides the user to the
right values. The manual procedure that works (print labeled test patterns,
observe, store the answer) was validated by hand on a Rongta RP850P — the wizard
automates exactly that procedure.

## Approach

A guided, print-and-ask wizard inside the **options flow**. The entry's adapter is
live while the options flow runs, so each step prints a short test pattern and
then shows a form asking one question about what came out. The wizard only fills
in **existing** per-entry options (`impl`, `width_pixels`, `line_width`,
`codepage`) — no new runtime code paths, so a wizard bug cannot break printing.

### Entry point

`OptionsFlow.async_step_init` becomes a **menu** (`async_show_menu`) with two
items:

- `settings` — the existing options form, unchanged (renamed step id; all
  current behavior preserved).
- `calibrate` — the wizard.

Known cost: every existing options-flow test gains one menu-selection hop.

### Wizard steps (in dependency order)

Each print happens on step entry, via the adapter's existing print pipeline
(executor + printer lock). Patterns are PIL images generated in a new module
`_config_flow/calibration_patterns.py` plus plain-text rulers; images bypass the
image-source resolvers (they are integration-generated, not user input — the
SSRF/path validation layers exist for untrusted sources). Every step's form
includes a "Reprint the test page" choice (re-enters the step) and can be
abandoned by closing the flow — nothing is stored until the final step.

1. **`calibrate_impl`** — prints three sections, each a text label line
   ("TEST 1/2/3" — text always works even when images garble) followed by a
   small checkerboard printed with `bitImageRaster` / `bitImageColumn` /
   `graphics` respectively. Question: "What is the first number whose pattern
   printed cleanly (a crisp checkerboard, no stray letters)?" → choices 1/2/3 /
   "none printed cleanly" / reprint. Result → pending `impl` ("none" → leave
   `auto`, show an explanatory abort-or-continue message since later image steps
   depend on a working impl; continuing uses raster).

2. **`calibrate_width`** — prints four bars at 384 / 512 / 576 / 640 px using
   the chosen impl, each labeled at its LEFT edge (labels survive right-edge
   clipping). Bars at or beyond the true printable width clip to identical
   length. Question: "Counting from the top, which is the first bar that is the
   same length as the bottom bar?" → 1/2/3/4 / "not sure" / reprint. Result →
   pending `width_pixels` (384/512/576/640; "not sure" → unchanged).

3. **`calibrate_ruler`** — prints a plain-ASCII column ruler
   (`....+...1|....+...2|` style out to 64 columns, tens digits embedded).
   Question: "What is the highest number fully visible on the FIRST line before
   it wraps?" → integer field (range 16–96) with the tens markers explained in
   the description. Result → pending `line_width`.

4. **`calibrate_codepage`** — **skippable** (first choice: "Skip this step").
   Prints numbered sample lines — `café ñ ü é ß ° €` encoded per candidate —
   candidates being the profile's codepages when a profile is set, else
   `COMMON_CODEPAGES` (CP437, CP850, CP858, CP1252, ISO_8859-1 — CP858/CP1252
   for the € sign). Question: "Which number shows all characters correctly?" →
   numbered choices / "none" / skip / reprint. Result → pending `codepage`
   ("none"/skip → unchanged).

5. **`calibrate_summary`** — shows the measured values via description
   placeholders, plus:
   - An optional **"Printer make & model"** text field (used only for the share
     link and prefilled into nothing else).
   - A **share link** in the step description: a prefilled GitHub new-issue URL
     (`https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/new`
     with URL-encoded `title="Printer calibration: <model>"` and a body
     containing model, measured impl/width/line-width/codepage, the configured
     profile, integration version, and python-escpos version). This is exactly
     the dataset an alias-table entry needs, hardware-verified by construction.
     The link is rendered via description placeholders; it must be built lazily
     and URL-encoded with `urllib.parse.quote`.
   - Submitting **saves**: new options = `{**entry.options, **measured}` —
     merging, never replacing, so untouched options (timeout, reliability
     profile, etc.) survive. Only this step writes anything.

### Failure handling

A print failure on step entry re-shows the step's form with
`errors["base"] = "calibration_print_failed"` (printer offline, transport error)
— the user can retry (resubmit/reprint) or abort the flow. No partial saves; the
flow aborting at any point leaves options untouched.

### Stretch (only if trivially reachable, else defer)

A `calibrate_impl` pre-step option "Print the printer's own settings page" using
the ESC/POS `GS ( A` test-print command. Requires a small raw-bytes adapter
method (only `printer._raw` exists internally today). Defer if it needs more
than a thin, locked wrapper.

## Out of scope

- Setup-time (config flow) calibration — printer entries must exist first;
  revisit after the options wizard proves out.
- Any automatic result detection — there is no feedback channel from the
  printer; the user's eyes are the sensor.
- Automatic alias-table submission — the GitHub link keeps a human in the loop.

## Testing

- Pattern generator unit tests: bar widths/labels, checkerboard dimensions,
  ruler string content (pure functions, no printer).
- Flow tests with a mocked adapter: menu routing; each step prints on entry
  (assert adapter call + payload class), stores the pending value, reprint
  re-prints, skip paths; summary merges into existing options without dropping
  untouched keys; print-failure path shows the error and does not save.
- Share-link test: URL contains encoded model + all measured values.
- Existing options-flow tests updated for the menu hop.

## Copy/translations

New menu + five steps in `strings.json`, mirrored in `translations/en.json`.
Questions phrased for non-technical users; every step description says what the
printer should have just printed.

## Changelog

Under the unreleased `## [1.1.0]` → Added: calibration wizard bullet naming the
four dialed-in settings and the share link.
