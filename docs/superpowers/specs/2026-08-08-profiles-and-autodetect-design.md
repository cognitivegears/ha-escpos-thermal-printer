# Printer profiles & autodetect improvements — design

**Date:** 2026-08-08
**Status:** approved design, pending implementation plan
**Version impact:** minor bump (1.0.0 → 1.1.0) — changes default image-implementation
resolution and removes `impl` from reliability presets (behavioral change for some
printers, see Piece 4).

## Problem

- "Auto-detect (Default)" in the profile dropdown detects nothing: it stores an empty
  profile string, python-escpos gets no profile, and image width silently falls back to
  384 px (`base_adapter.py` `_get_target_width`). Unlisted printers hit a Repairs issue
  with no user-side fix.
- USB discovery reads product descriptor strings and matches `THERMAL_PRINTER_VIDS`,
  but neither feeds the profile choice — the user always picks from a flat ~35-entry
  dropdown.
- The bundled escpos-printer-db snapshot (python-escpos 3.1) has 35 profiles; clones
  (Xprinter, Zijiang, rebadged Citizens, …) are mostly absent, and no clone→equivalent
  mapping exists anywhere upstream.
- Image implementation (`impl`) defaults to `bitImageRaster` from reliability presets
  regardless of printer. Profile feature flags (`graphics`/`bitImageRaster`/
  `bitImageColumn`) are never consulted; `profile_supports_feature()` has zero
  production callers. Column-only printers (TM-U220) and no-image profiles garble.

## Research findings that shape the design

- python-escpos consumes only four profile fields at runtime/config time in this
  integration: `media.width.pixels` (image sizing — the only runtime one), `codePages`,
  font `columns`, and cut flags.
- Bundled feature-flag data: `bitImageRaster` 30/35 profiles, `bitImageColumn` 29/35,
  `graphics` 22/35. Every profile with `graphics` also has raster, so raster strictly
  dominates for compatibility. Clone-family profiles (`simple`, POS-5890, Sunmi-V2)
  are raster-only; TM-U220/U220B are column-only.
- Profile trustworthiness is split: width/dpi/codepages/fonts are hand-customized by
  contributors; `features` blocks are frequently inherited verbatim from `default` and
  never hardware-verified (confirmed via git history for CT-S651).
- Citizen CT-S601-family garbling can be caused printer-side by the MSW10-4 emulation
  memory switch (ESC/POS vs legacy CBM modes) — no profile can fix that.

**Design principle:** profile/alias data *improves defaults, never gates behavior*.
Width, codepages, and columns are trusted; feature flags are hints. An explicit user
request to print is always attempted (with a warning if the profile disagrees).

## Piece 1 — Per-entry width override + honest naming

- Add optional `CONF_WIDTH_PIXELS = "width_pixels"` to config-flow settings step and
  options flow (all four transports). Voluptuous `Range(16, 2048)` (same bounds as the
  per-call `width` validation). Stored per entry, options-over-data like `CONF_PROFILE`.
- `BasePrinterConfig` gains `width_pixels: int | None = None`.
- `_get_target_width()` order: entry `width_pixels` → profile `media.width.pixels` →
  384 fallback. When the override is set, skip the `profile_width_fallback` Repairs
  issue entirely; update the Repairs issue text to point at the new field as the fix.
- Rename the dropdown label `"Auto-detect (Default)"` → `"Generic (no profile)"` in
  `capabilities/profiles.py`. Value stays `""` — no migration needed.

## Piece 2 — USB profile suggestion

New module `capabilities/suggestions.py`:

- `suggest_profile(product: str | None, vid: int | None, pid: int | None) -> str | None`
  1. Normalize the USB product descriptor (casefold, strip non-alphanumerics) and
     substring-match against normalized profile names and alias keys (Piece 3) —
     descriptors like "TM-T20II" carry the model name and beat any PID table.
  2. Fall back to a small curated `(vid, pid) → profile` dict. Seed:
     `(0x0416, 0x5011) → "POS-5890"` (Zijiang family). Epson (0x04b8) gets no blanket
     mapping — name-match handles it; a wrong specific model is worse than none.
- USB config-flow steps pass the enumerated device's descriptor through and use the
  suggestion as the dropdown *default* (preselected, user can change). No suggestion →
  current behavior unchanged. Never auto-commits a profile without the user seeing it.

## Piece 3 — Clone/equivalence alias table

New module `capabilities/aliases.py`:

- `PROFILE_ALIASES: dict[str, str]` — normalized alias → bundled profile name. Each
  entry carries a comment citing its basis. Seed small (grow via user reports):
  - `CT-S601`, `CT-S601II`, `CT-S651II` → `CT-S651` (same Citizen family, shared
    command reference, verified same 80 mm/640 px/203 dpi class; S801/S851 excluded
    until their dpi is verified).
  - `ZJ-5890`, `POS-5890K`, `ZJ-5890K` → `POS-5890` (same Zijiang hardware family).
- Consumers:
  - `suggest_profile()` name matching (Piece 2).
  - The custom-profile-name step: `is_valid_profile()` resolution accepts an alias and
    resolves it to the real profile before storing — typing "CT-S601II" works.
- Aliases do **not** appear as extra dropdown entries (keeps the list short) and never
  gate anything — they only route a user to an existing profile's width/codepages.
- Process note: genuinely new hardware (measured width, tested codepages) should be
  contributed upstream to escpos-printer-db; the alias table is for rebadges and
  near-equivalents only.

## Piece 4 — Profile-driven impl auto-pick

- Remove `impl` from every `RELIABILITY_PROFILE_PRESETS` entry. Presets become pure
  transport pacing (`fragment_height` + `chunk_delay_ms`); image implementation is a
  printer property, not a transport property. **This is the behavioral change driving
  the minor version bump**: users on a named preset with a column-only or no-image
  profile stop getting hardcoded raster.
- New helper in `capabilities/features.py` (finally a production caller):
  `pick_impl(profile_name: str) -> str | None`
  - profile claims `bitImageRaster` → `"bitImageRaster"`
  - else claims `bitImageColumn` → `"bitImageColumn"` (TM-U220-class impact printers)
  - else (no image features, or no/unknown profile) → `None`
  - `graphics` is never auto-picked — raster is available everywhere graphics is; it
    stays a manual choice.
- Resolution chain in `prepare_image()` (`image_operations.py`), first hit wins:
  1. per-call `impl` (service data)
  2. per-entry `CONF_IMPL` when not `"auto"` (Piece 5)
  3. `pick_impl(profile)`
  4. `DEFAULT_IMPL` (`bitImageRaster`) — and if the profile explicitly claims *no*
     image support, log a one-time-per-entry warning ("profile X reports no image
     support; attempting bitImageRaster anyway") and still print. Warn-but-try:
     feature flags are hints, an explicit user request is honored.

## Piece 5 — impl as a first-class config option

- Add `CONF_IMPL = "impl"` per entry (settings step + options flow), default `"auto"`.
  Choices with plain-language labels:
  - `auto` — "Auto (recommended): follow the printer profile"
  - `bitImageRaster` — "Raster — works on most printers"
  - `bitImageColumn` — "Column — older/impact printers; try this if images print as
    garbled text"
  - `graphics` — "Graphics — modern Epson printers"
- Feeds step 2 of the resolution chain. Per-call `impl` in service data still wins.
- Update the `impl` field description in `services.yaml` to mention the garbled-text
  symptom. This touches all six image-service blocks in lockstep (field-set parity
  invariant, `test_image_services_share_common_field_metadata`); quote descriptions
  containing `#`; regenerate translations via `scripts/sync_service_translations.py`.

## Out of scope (deliberate)

- Full user-authored profiles (codepages/features/fonts editor, constructed
  `escpos.capabilities.Profile` objects, `ESCPOS_CAPABILITIES_FILE`): width override +
  existing codepage/line-width overrides cover the real cases at a fraction of the
  surface. Revisit only on concrete user demand.
- `GS I` hardware interrogation: no prior art, needs response handshaking, reliability
  on clones unknown. Roadmap candidate at best.
- Shipping our own capabilities database: stay on the python-escpos snapshot;
  contribute upstream instead.

## Testing

- Piece 1: unit test — entry `width_pixels` beats profile width; no Repairs issue when
  set; `Range` bounds enforced in flow.
- Piece 2: `suggest_profile()` table tests — "TM-T20II" descriptor → `TM-T20II`;
  `(0x0416, 0x5011)` → `POS-5890`; garbage/None inputs → `None`. Flow test: suggested
  profile preselected, user override respected.
- Piece 3: alias resolution in the custom-profile step ("CT-S601II" stores
  `CT-S651`); every alias target exists in the bundled DB (guard test).
- Piece 4: `pick_impl` — TM-T20II → raster, TM-U220 → column, AF-240 → None,
  unknown/empty → None; warning logged once per entry on the no-image path; presets no
  longer contain `impl`.
- Piece 5: resolution-chain test (call beats entry beats profile beats default);
  services.yaml parity and truncation tests stay green.
- Existing config-flow tests asserting the old "Auto-detect (Default)" label updated
  to "Generic (no profile)".

## Release notes

- CHANGELOG `## [Unreleased]`: entries for all five pieces, flagging the Piece 4
  default-resolution change as behavioral.
- Version 1.1.0 in `manifest.json` + `pyproject.toml` at release.
