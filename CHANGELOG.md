# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Breaking changes

- **`blueprints/automation/escpos_printer/todo_item.yaml`** input
  renamed from `box_style` → `style` to match the convention used by
  every other blueprint in the pack (the 5 new ones, plus the 8
  pre-existing). Existing scripts created from this blueprint will need
  to be re-saved (HA will show the input as unset on the next edit and
  default it to `auto`). The single-input change is otherwise
  semantically identical — same border-style options, same default.

### Added

- **`blueprints/automation/escpos_printer/doorbell_snapshot.yaml`** —
  on doorbell button / motion / state-trigger entity firing, prints a
  titled camera snapshot (via `print_camera_snapshot`) with a "From /
  Time" footer. Configurable rotation, dither mode, and border style.
  The snapshot service call carries `continue_on_error: true` so a
  camera that's offline or mid-reboot still produces the title +
  timestamp slip rather than silently skipping the whole automation.
- **`blueprints/automation/escpos_printer/morning_briefing.yaml`** —
  single morning slip combining a date header, optional weather
  forecast table, optional today's calendar agenda, and a templated
  one-line footer. Each section is independently optional — leave the
  matching entity blank to skip. Defensive against null `temperature` /
  `condition` from providers (accuweather, met.no fallback) and against
  all-day calendar events (which return `start` as `{date: "..."}`
  rather than a string — caught both crashes during pre-merge review).
- **`blueprints/automation/escpos_printer/trash_reminder.yaml`** —
  fires daily at a configured time and looks at the target weekday
  (`offset_days` default 1 = tomorrow's bins; set to 0 with an earlier
  `print_time` for a morning-of reminder). Seven per-weekday text
  inputs hold bin descriptions; empty days silently skip so the
  reminder only prints on the actual pickup days.
- **`blueprints/automation/escpos_printer/todo_ticket.yaml`** —
  upgraded counterpart to `todo_item`. Per new task, prints a
  job-ticket slip with a bold double-width title (pure text mode —
  works on image-less printers), a Due / List / Added KV table,
  optional description, and a QR code linking back to the source task.
  `url_template` is a Jinja template with `uid` / `summary` / `due` /
  `description` in scope (default targets Todoist's web URL); QR
  auto-skips when `uid` is empty so the blueprint is safe across mixed
  back-ends (local lists, Google Tasks). Header text ("NEW TASK") is
  configurable via the `header_text` input. New-item detection diffs
  on `uid` first (with summary fallback) so two tasks with the same
  title don't dedup and renames don't look like add+drop.
- **`blueprints/script/escpos_printer/guest_wifi_qr.yaml`** — prints
  a scannable Wi-Fi QR encoding the standard
  `WIFI:T:<auth>;S:<ssid>;P:<pass>;H:<hidden>;;` URI (supported by iOS
  / Android / most laptop camera apps), with proper backslash-escaping
  of reserved characters in SSID and password, plus optional plaintext
  fallback for devices without a QR scanner.
- **`blueprints/UNIFI_GUEST_WIFI.md`** — opinionated, ~10-minute
  recipe pairing the Guest Wi-Fi QR blueprint with the **official HA
  UniFi integration**. One shell script (`unifi_wifi.sh` with `read` /
  `rotate` actions) that pulls credentials directly from HA's existing
  UniFi config entry (`.storage/core.config_entries`) via `jq` — no
  `.env` dotfiles, no separate `input_text` helpers, no `secrets.yaml`
  edit, no duplicate secret storage. The script handles UniFi OS
  cookie auth + CSRF token extraction; rotation generates a 16-char
  password from a visually-readable alphabet (57-char set, ~93 bits)
  and PUTs the partial-document update. Rotation password generation
  uses scoped `set +o pipefail` to dodge `tr | head` SIGPIPE plus a
  length-postcondition assertion. HA wiring is one `command_line:`
  sensor (hourly poll), one `shell_command:`, one HA script (rotate →
  refresh sensor → wait for the sensor to reflect the rotated value →
  print), one monthly automation, two Lovelace buttons (Print current
  / Rotate now). 5-step setup with a verification checklist and a
  top-5 gotcha list. Linked from `blueprints/README.md` under
  "Integration recipes." Security-model section covers where
  credentials live, argv visibility window, tempfile cleanup, password
  strength + alphabet inconsistency, printed-paper exposure, recorder
  DB retention, and the on-LAN MITM threat model for `--insecure`.
- **`blueprints/README.md`** — table rows, import badges, and
  per-blueprint notes for the five new entries (including
  back-end-specific URL patterns for the TODO Ticket blueprint, an
  emoji-rendering caveat for text-mode summaries, and a TODO Item /
  TODO Ticket decision rule). Slimmed from 336 → 147 lines after
  splitting two long sections into their own files (see below); now
  acts as the catalogue index with brief per-blueprint notes and
  pointers to the deeper guides.
- **`blueprints/AUTHORING.md`** (new) — the full blueprint-authoring
  guide split out of the README. Covers the drop-in workflow for
  private blueprints, key HA concepts (`!input` substitution,
  `mode:` placement, selectors, Jinja rendering at call time),
  minimal script + automation shapes, a three-tier
  **"Validating your blueprint"** section (HA's on-import check /
  generic `yamllint` / this repo's strict `validate_blueprints.py`
  service-call lint plus the markdown-bash extractor), publishing
  via raw GitHub URL, the repo-specific conventions for contributors
  (file location, sanitiser chain, `print_text_utf8` vs
  `print_text`, the validator + extractor + markdown-lint
  pipeline), modifying existing blueprints, and resources. Closes
  the discoverability gap where the only authoring guidance lived
  in `CLAUDE.md`.
- **`blueprints/GUEST_WIFI_QR.md`** (new) — Guest Wi-Fi QR setup
  guide split out of the README's per-blueprint notes (which had
  grown to ~65 lines of effectively-a-tutorial under what should be
  a 3-line note). Covers the 2-minute Quick start, helper-backed
  credentials, automated rotation pointer, and ZXing WIFI URI
  format details. `UNIFI_GUEST_WIFI.md`'s "Don't need automation?"
  callout now points here rather than at the README. The Guest Wi-Fi QR section now leads
  with a "Quick start (works on any router — about 2 minutes)" 6-step
  walk-through that gets a non-technical user from blueprint import
  to a printed scan-ready slip without touching YAML or shell
  scripts. Beneath it: a "store credentials in helpers" step for
  users who want to edit creds without editing the script, and an
  "Automating rotation" section that covers UniFi (link to deep
  doc), other API-capable routers, and the manual-rotate-with-
  reminder fallback for ISP modems / consumer APs with no API.
  Format / ZXing details moved to the bottom so they don't
  intimidate first-time users. Includes a security note about the
  TODO Ticket `url_template` input — it's rendered with HA's full
  template scope, so a malicious fork could exfiltrate secrets via
  the QR payload (humans don't read QRs; their phones do).

### Fixed

- **`blueprints/automation/escpos_printer/trash_reminder.yaml`** —
  inlined `now() + timedelta(...)` into the `target_day_name` /
  `target_label` templates. HA's `render_complex` evaluates each
  `variables:` entry with `parse_result=True`, which stringifies any
  datetime stored in an intermediate variable; the next template's
  `target_date.strftime(...)` then crashed with
  `'str object' has no attribute 'strftime'`. Computing the date inline
  keeps the datetime native to the expression. Caught by
  `tests/test_blueprints_template_safety.py` once the new blueprint
  gained a sandbox render case.

### Changed

- **`blueprints/script/escpos_printer/recipe_card.yaml` and
  `receipt.yaml`** — both bundled scripts swapped their large serif
  header from `print_text_image` (raster) to `print_text_utf8`
  (double-width / double-height / bold, text-mode). The
  image-rendered headers looked nicer but failed silently on the
  many ESC/POS printers that don't implement the raster image
  command family (notably several Bluetooth POS-58 units and
  budget USB models). Text-mode headers print on every supported
  printer and still transcode UTF-8 (accents, smart quotes) via the
  codepage. Users who specifically want the typographic header can
  re-add `print_text_image` in a fork — it's a one-line change in
  each blueprint.
- **`blueprints/script/escpos_printer/recipe_card.yaml` and
  `blueprints/automation/escpos_printer/todo_ticket.yaml`** — text
  sanitiser chain now strips `\r` (left over from Windows `\r\n` line
  endings after splitting on `\n`) in ingredient/step rows and in
  task descriptions. Previously, pasted-from-Windows content rendered
  with stray carriage returns. `\n` is still preserved inside
  multi-paragraph task descriptions (`print_text_utf8` wraps them
  correctly).

### Added (CI / tooling)

- **`scripts/extract_markdown_bash.py`** — extracts fenced ```bash```
  blocks from `blueprints/*.md`, writes them to tempfiles, runs
  `shellcheck`, and (for blocks that include the password-generator
  pipeline) executes the pipeline 10 times under `set -euo pipefail`
  to assert `rc=0` and `len=16`. Catches the SIGPIPE-class bug that
  shipped in the rotation script during this branch's pre-merge
  review.
- **`scripts/validate_blueprints.py`** extended with a service-call
  lint that cross-references every `service: escpos_printer.<name>`
  call against `custom_components/escpos_printer/services.yaml`,
  asserts each `<name>` is registered, and validates field names in
  each `data:` block against the service's voluptuous schema. Catches
  service-name typos and field-name drift across the 13 bundled
  blueprints.
- **`tests/test_blueprints_yaml.py`** gained two regression tests for
  the new service-call lint: typo'd service name (`print_text_utf`
  missing `8`) must be flagged; unknown data field on a valid service
  must be flagged. **`tests/test_markdown_bash.py`** added with three
  cases: bundled markdown lints cleanly; a fixture re-introducing the
  SIGPIPE pattern must trip the warning; a fixture with the scoped
  pipefail + length assertion must pass.
- **`pymarkdown`** wired in via pre-commit (config at
  `.pymarkdown.json`) — disables MD013 (line length, incompatible with
  prose-style markdown), MD036 (bold-as-pseudo-heading is intentional
  for `**Inputs:**` / `**Notes:**` in-paragraph labels), narrows MD024
  to siblings-only (so the CHANGELOG's repeated `### Added` headings
  under different `## [version]` parents are allowed), and disables
  MD041 (first-line top-level-heading false positive for
  callout-prefixed docs). Hook scope: **every `.md` file** the repo
  tracks (excluding `dist/`, `.full-review/`, build / cache dirs).
  All 31 existing markdown files now lint clean.
- **`scripts/md_fix.py`** — safe targeted fixer for MD022 / MD031 /
  MD032 / MD040 (the four "missing blank lines" / "missing language
  tag" rules that account for >95% of findings on existing docs).
  Required because `pymarkdown fix` has two demonstrated bugs against
  this repo's prose: (1) rewrites `+` conjunctions in continuation
  lines to `-` list markers, breaking sentence meaning (caught in
  `CLAUDE.md` / `.github/PULL_REQUEST_TEMPLATE.md`); (2) outdents
  fenced code blocks indented inside list items, breaking the list
  structure (caught in `docs/troubleshooting.md` /
  `tests/integration_tests/README.md`). `md_fix.py` is fence-aware
  (never touches code-block interior), never alters list-marker
  characters, never adjusts indentation. Reduces a 74-finding
  scan-result over the full doc set to 3 findings in one pass.
- **`.pre-commit-config.yaml`** — the `validate-blueprints` hook's
  file scope widened to `.yaml|.yml`; new `extract-markdown-bash` hook
  fires on `blueprints/*.md` changes; new `pymarkdown` hook fires on
  any tracked markdown file.

## [0.7.0] - 2026-05-24

### Breaking changes

- **Preview-service `output_path` is now restricted to the system
  tempdir.** `preview_image`, `preview_box`, and `preview_table`
  previously accepted any path inside `allowlist_external_dirs`. After
  security hardening (a non-admin HA user could otherwise call
  `preview_image` with `output_path: /config/configuration.yaml` and
  clobber it with rendered PNG bytes — CWE-862/CWE-552), user-supplied
  `output_path` values outside the system temp directory are rejected
  with `HomeAssistantError`. If your automation needs the file in
  `/config/www/`, add a second step that copies the returned `path`.

### Added

- **Text-effects services** — seven new services for receipt-style
  layouts that work within the 1-col-per-glyph thermal text mode:
  - `escpos_printer.print_box` — wraps text in a printable border.
    `style: auto` picks Unicode single-line `┌─┐` on CP437-capable
    profiles and falls back to ASCII (`+-+`) elsewhere; explicit
    `single` / `double` / `ascii` / `asterisk` / `hash` are honored
    when the user wants a specific look.
  - `escpos_printer.print_table` — multi-column rows with per-column
    `column_aligns` (`left` / `center` / `right`), optional header
    separator, and the same border-style picker as `print_box`.
  - `escpos_printer.print_kvtable` — two-column label/value pairs
    (subtotals, sensor readings, receipt totals) with auto-aligned
    values on the right edge of the printable width.
  - `escpos_printer.print_separator` — a single decorative rule
    (line of repeated characters) at the current printable width.
  - `escpos_printer.print_text_image` — renders text via a TTF/OTF
    font (DejaVu trio bundled, custom fonts dropped into
    `<config>/fonts/` or anywhere in `allowlist_external_dirs`),
    rasterises to a 1-bit image, and prints. Supports 90/180/270°
    rotation, font size, alignment, threshold dither — useful for
    glyphs the printer's codepage doesn't carry (CJK, emoji,
    decorative scripts).
  - `escpos_printer.preview_box` / `escpos_printer.preview_table` —
    render the same layouts to a `.txt` file in the system tempdir
    (default `/tmp/escpos_preview_<entry>.txt`) without printing, so
    users can tune column widths and border styles without burning
    paper. Returns `{path, width, line_count, codepage}` so a
    follow-up step can copy the file or chain a notification.
- **Bundled DejaVu fonts** — `DejaVuSans.ttf`, `DejaVuSansMono.ttf`,
  `DejaVuSerif.ttf` (release 2.37) ship with the integration for
  `print_text_image` to work out of the box. Bitstream Vera license
  text included at `custom_components/escpos_printer/fonts/LICENSE`
  and `NOTICE` at the repo root.
- **Auto-created `<config>/fonts/` directory** on integration setup.
  Any TTF/OTF dropped in is trusted by `print_text_image.font_path`
  without needing an `allowlist_external_dirs` entry — removes the
  "I dropped a font in /config/fonts/ and got an allowlist error"
  friction. Files anywhere else still go through the standard
  allowlist check.
- **Bundled HA blueprints** in `blueprints/` — eight ready-to-import
  scripts and automations exercising the text-effects services:
  - Scripts: `shopping_list`, `todo_list`, `weather_forecast`,
    `receipt`, `recipe_card`.
  - Automations: `daily_agenda`, `sensor_alert`, `todo_item`.
  - `blueprints/README.md` documents import instructions, per-input
    semantics, and troubleshooting.
- **`scripts/validate_blueprints.py`** — YAML structural validator
  that tolerates HA's custom `!input` tag, enforces that each
  blueprint sits under a directory matching its
  `blueprint.domain` (`script` or `automation`), and is wired into
  pre-commit via the new `validate-blueprints` hook plus a CI test
  in `tests/test_blueprints_yaml.py`.
- **`wcwidth==0.2.13`** runtime dependency — `text_effects.width`
  uses it for visual-column measurement so CJK / fullwidth / emoji
  columns line up correctly under the printer's 1-col-per-glyph text
  mode (a naive `len()` silently misaligns).
- **`security.validate_font_path()`** — validates `print_text_image`
  font paths for extension (`.ttf` / `.otf`), file size, symlink
  resolution, and regular-file status, independent of where the path
  lives.
- **`security.validate_rows()`** — typed validator for `print_table`
  rows that enforces consistent column counts, coerces cells to
  strings, and bounds total cell count to protect against
  paper-waste DoS.
- **`security.open_local_font_no_follow()` / `open_local_image_no_follow()`**
  — shared `O_NOFOLLOW`-based reader used by font and image
  validators (refactored from the existing image-only path).

### Changed

- **Pre-commit `check-yaml` runs with `--unsafe`** to tolerate the
  `!input` and other HA custom tags in `blueprints/`. The dedicated
  `validate-blueprints` hook does the structural validation.

### Security

- **DNS rebinding defence for HTTP image fetches.** Each
  `print_image` / `preview_image` HTTP fetch builds a per-request
  `aiohttp` session pinned to the IP address validated by
  `getaddrinfo` (via the new `image_sources._StaticResolver`). A
  0-TTL hostile DNS server cannot swap public → private between
  validation and connect. The previous httpx fast-path was removed
  (httpx 0.28 has no resolver-pin hook). **CWE-918 / CWE-350.**
- **Preview `output_path` restricted to system tempdir.** Closes a
  privilege-escalation path where a non-admin HA user could call
  `preview_image` / `preview_box` / `preview_table` with
  `output_path: /config/configuration.yaml` and clobber it with
  rendered bytes. See *Breaking changes*. **CWE-862 / CWE-552.**
- **Preview file writes use `O_NOFOLLOW`.** A co-resident attacker
  who plants a symlink between path-validation and image-save
  cannot redirect the write into an arbitrary file under tempdir.
  New `security.write_file_no_follow` primitive, symmetric to the
  existing `open_local_*_no_follow` readers. **CWE-367 / CWE-59.**
- **IDN hostname check IDNA-encodes first.** The previous
  `"xn--" in hostname.lower()` substring test missed raw Unicode
  hostnames (`例え.テスト`); the check now IDNA-encodes before the
  substring test so raw-Unicode and pre-encoded inputs are both
  caught. **CWE-918.**
- **`control_handlers.py` error messages go through
  `sanitize_log_message`.** `feed` / `cut` / `beep` previously
  wrapped exceptions with raw `str(err)`, which routinely contains
  USB serials, BT MACs, and filesystem paths from pyusb / pyserial
  / python-escpos / aiohttp. All handlers now route through the
  shared `_for_each_target` helper in
  `services/_handler_utils.py`. **CWE-209 / CWE-532.**
- **`asyncio.shield` cleanup on print_text_with_image cancel.** A
  second cancellation mid-flush can no longer leave paper half-
  printed.
- **Font-path trust centralised in `security.py`.** The
  `<config>/fonts/` narrowed-trust decision now lives in
  `validate_font_path_with_fonts_dir()` next to the other
  path-validation policy, instead of split between
  `print_handlers.py` and `security.py`.
- **DNS-rebinding hardening also applies to redirects.** Each
  redirect hop in `_resolve_http_aiohttp` runs through the validator
  again and gets a fresh DNS pin via a new `_StaticResolver`.
- **Status-vs-print serialisation hardened** — network / USB /
  Bluetooth `_status_check` skip when the per-adapter print lock
  is held, eliminating a flap-during-print race on bandwidth-
  constrained transports.
- **Dismissed HA-pinned-package Dependabot security alerts** as
  `tolerable_risk` (Pillow direct + uv.lock transitives: aiohttp,
  cryptography, pyOpenSSL, PyJWT, orjson, requests, uv, pytest).
  All are pinned by HA core / `pytest-homeassistant-custom-component`
  and bumping ahead of HA breaks installs; dev/CI-only exposure;
  end users install via `manifest.json`. They will auto-re-surface
  if new advisories arrive against the HA-pinned versions.
- **Added `pillow` and `respx` to the Dependabot version-update
  ignore list** in `.github/dependabot.yml` (alongside the
  existing `pytest` and `dbus-fast` entries) so version-bump PRs
  stop being re-opened against the HA-driven pins.

## [0.6.0] - 2026-05-17

### Added

- **Preview without printing.** New `escpos_printer.preview_image` service
  runs the full image pipeline (dither, resize, rotate, invert, mirror)
  and writes the resulting 1-bit PNG to disk *without* printing it.
  Returns `{path, width, height, slice_count}` so automations can chain
  a notification. Tune `dither`/`threshold`/`image_width` in Developer
  Tools instead of burning paper.
- **Focused convenience services.** `print_camera_snapshot`,
  `print_image_entity`, `print_image_url`, and `print_image_path` —
  each takes only the relevant field with a proper UI selector (camera/
  image entity picker; URL or path text), funneling into the same handler
  as `print_image`. All focused services now expose the **full image
  option set** (rotation, mirror, invert, autocontrast, threshold,
  dither, alignment, center, high-density, cut, feed) inline, with rarely-
  used reliability knobs (`impl`, `fragment_height`, `chunk_delay_ms`,
  `fallback_image`) collapsed under `advanced: true` so the default form
  stays readable.
- **Calibration print.** `escpos_printer.calibration_print` prints a
  ruler + a threshold-sweep strip so users pick the right
  `dither: threshold` value without trial-and-error roll burning.
- **Per-printer reliability profile** in the Options flow:
  *Auto / Fast LAN / Balanced / Conservative / Bluetooth-safe*. Each
  profile presets `fragment_height` + `chunk_delay_ms` + `impl`.
  Bluetooth entries default to *Bluetooth-safe*; everyone else to
  *Auto*. Service-call options always override.
- **`invert` and `mirror` options** for `print_image` / notify image
  attachments (white-on-black logos, dark-mode QRs, receipt-window
  displays).
- **`auto_resize` option** — accepts source images up to 40 MB and
  downscales them before processing. Removes the friction of "image
  too large" errors on iPhone HEIC / high-res camera snapshots.
- **`fallback_image` option** — if the primary source fails to
  resolve (camera unavailable, URL down, file missing), the integration
  retries the fallback once. Camera/HTTP sources also get a single
  automatic retry with a 500 ms back-off.
- **HEIC / HEIF / AVIF support** when `pillow-heif` is installed (soft
  dependency — no impact on existing setups). iOS-fed camera proxies
  emit HEIC natively.
- **Notify entity accepts unprefixed image keys** — `dither`, `threshold`,
  `rotation`, `invert`, etc. work on `notify.<printer>` without the
  `image_` prefix. Prefixed names still work; prefixed wins on collision.
- **Repair issue** when the printer profile doesn't expose
  `media.width.pixels`. Surfaces the silent 512-px fallback in the HA
  UI with actionable guidance instead of a buried log line.
- **Last image-print diagnostic sensor** — exposes `total_prints`,
  `total_failures`, decoded dimensions, slice count, last error class
  as a polled diagnostic sensor on each printer device.
- **Plain-English `impl` dropdown labels** in the UI — "Raster
  (default — Epson)" / "Graphics (newer ESC/POS)" / "Column (legacy
  POS-58/80)" instead of the raw python-escpos identifiers.
- **Image sources for `print_image` and notify entities.** `image:` now
  accepts URLs (`http://`, `https://`), local file paths, Home Assistant
  camera entities (`camera.<id>`), image entities (`image.<id>`), base64
  data URIs, and Jinja templates that render to any of the above. See
  `docs/images.md`.
- **New `print_image` options** — `image_width`, `rotation`, `dither`
  (`floyd-steinberg` / `none` / `threshold`), `threshold`, `impl`
  (`bitImageRaster` / `graphics` / `bitImageColumn`), `center`,
  `autocontrast`, `fragment_height`, `chunk_delay_ms`. Defaults are
  populated in `services.yaml` so the UI form pre-fills them.
- **`notify.<printer>` accepts an `image:` attachment** plus the same
  options (with `image_` prefix). Text and image now print as a single
  uninterrupted receipt under a single printer-lock acquisition.
- **Auto-resize to the printer profile's pixel width.** When `image_width`
  is omitted, the integration uses the python-escpos profile's
  `media.width.pixels` (cached per adapter; falls back to 512 px with a
  one-time WARNING when the profile doesn't expose it).
- **Image-pipeline diagnostics** in `runtime.image_pipeline` of the
  config-entry diagnostics dump (source kind, last decoded dimensions,
  total prints / failures, last error class — never URLs or paths).
- **GitHub issue template `bug-image.yml`** for structured image-bug
  reports (HA version, printer profile, source kind, image dimensions).
- **Semgrep rules** under `.github/semgrep/escpos.yml` enforcing
  project-specific patterns (no raw `aiohttp.ClientSession()`, no
  `os.path.normpath` in validators, etc.).

### Changed

- **Atomic notify text+image.** `notify.print_message` no longer makes
  two separate adapter calls; a new `print_text_with_image` adapter
  method acquires the printer lock once and runs both halves under it,
  so another caller can't interleave between the text and image halves.
  Image bytes are pre-resolved *outside* the lock so a slow camera
  doesn't monopolize the printer.
- **Default `chunk_delay_ms` is now strictly transport-bound** — the
  schema no longer carries a 50 ms default that penalized Network/USB
  callers. Network/USB defaults to 0 ms, Bluetooth to 50 ms, and the
  per-printer Reliability profile can override either.
- **`impl` and `fragment_height` no longer have schema-level defaults**
  — they fall through to the per-printer Reliability profile (Auto
  picks `bitImageRaster` / 256). Service-call values always win.
- **`MAX_PROCESSED_HEIGHT` error message** now suggests `image_width` /
  `rotation` as the concrete fix instead of just naming the cap.
- **Notify entity image fields** accept both `dither` and `image_dither`
  forms. The historic `image_` prefix is still honored for back-compat
  but no longer mandatory for image-only options.
- **`floyd-steinberg` dithers in-module** rather than deferring to
  python-escpos, so behaviour is deterministic across python-escpos
  versions. Pipeline reorders conversion-to-grayscale before
  rotate/resize for a ~3-4× speedup and ~3× peak-memory reduction on
  RGBA inputs.
- **RGBA / alpha-channel images are flattened onto a white background**
  before dithering — transparent pixels now render as white on the
  paper instead of black.
- **Pillow pinned to `==12.0.0`** in `pyproject.toml` for dev/CI
  reproducibility. `manifest.json` keeps a range to match Home Assistant
  core's bundled Pillow at runtime. `scripts/check_requirements_sync.py`
  now fails CI if any pyproject dependency is added without an `==` pin.

### Security

- **SSRF protection for HTTP image fetches.** URLs are validated for
  scheme, hostname, length, credentials, IDN/punycode, and port; the
  hostname is resolved via `socket.getaddrinfo` and the request is
  rejected if any resolved address is private, loopback, link-local,
  reserved, multicast, or unspecified. HTTP redirects are followed
  manually and each redirect target is re-validated. Previously the
  HTTP fetcher inherited zero SSRF protection from HA's httpx client
  (a documentation claim that was incorrect).
- **Allowlist enforcement on local file paths.** Paths outside
  `allowlist_external_dirs` are now rejected with `HomeAssistantError`.
  Previously the path was logged at DEBUG level and read anyway.
- **Symlink traversal blocked.** `Path.resolve(strict=True)` dereferences
  symlinks during validation; the file is then opened with `O_NOFOLLOW`
  so a TOCTOU swap between validation and open is also defeated.
- **Camera / image entity reads now check user permissions.** Callers
  without `POLICY_READ` on the named entity receive `Unauthorized`
  (403 from REST / WebSocket).
- **Pillow decompression bombs raise reliably.** `Image.MAX_IMAGE_PIXELS`
  is set process-globally and the broad `except Exception` around
  `ImageOps.exif_transpose` is narrowed so `DecompressionBombError`
  propagates instead of being swallowed.
- **`Image.open` is invoked with a pinned `formats=` allow-list**
  (`PNG`, `JPEG`, `GIF`, `BMP`, `TIFF`, `WEBP`) so attacker-controlled
  bytes can't reach novelty / vulnerability-prone decoders.
- **Base64 data URIs are size-capped before decoding** so a 200 MB
  payload no longer OOMs the process; the subtype regex is pinned to
  raster image formats (no `svg+xml`).
- **HTTP body is streamed with a mid-stream size cap** and
  `Content-Length` is honored before reading. Connection / per-chunk
  read timeouts replace the single total timeout.
- **`_resolve_http` aiohttp fallback narrowed** to `ImportError` only
  (previously triggered on every httpx exception including HTTP 4xx
  — which silently bypassed HA's middleware) and now uses HA's pooled
  `async_get_clientsession(hass)` rather than constructing a per-request
  `ClientSession`.
- **Log redaction extended.** `sanitize_log_message` now also redacts
  URL userinfo (`https://user:pass@host/...` → `https://[REDACTED]@host/...`)
  and HA filesystem paths (`/config/`, `/media/`, `/share/`, `/ssl/`,
  `/addon_configs/`, `/data/`). New default field names: `url`, `path`,
  `host`, `image`, `source`.
- **Quality-scale Bronze `action-setup` rule.** Every action registered
  via `hass.services.async_register` now passes `schema=...`. REST,
  WebSocket, and Python-script callers no longer bypass UI-level
  validation.
- **Bandit scope widened** to include `scripts/` (the dependabot-sync
  script runs with `contents: write`).
- **Notify error log sanitized.** `notify.print_message` no longer
  emits raw exception text at ERROR level (which would leak URL
  credentials, file paths, and Pillow byte fragments). Errors are
  wrapped in `HomeAssistantError(sanitize_log_message(str(err)))` and
  re-raised; the entity-platform framework logs them once.

### Fixed

- `_resolve_http` aiohttp fallback no longer raises `UnboundLocalError`
  when `session.get()` raises (the `finally`-block referenced an
  unbound `resp`).
- `print_qr` now calls `_mark_success()` so the binary-sensor status
  refreshes after a successful QR print (parity with `print_text` and
  `print_image`).
- Eager slice materialisation in `print_image` removed — slices are
  cropped just-in-time inside the send loop, roughly halving peak
  resident memory on tall images.
- Pipeline now enforces a `MAX_PROCESSED_HEIGHT = 8192` cap and a
  `MAX_SLICES = 64` cap per print — protects against paper-waste DoS.
- `print_image` cancellation now applies a best-effort cut+feed in a
  `finally` block, so cancelling mid-loop no longer leaves the paper
  mid-image.

### Performance

- Image processing pipeline reordered (convert to grayscale before
  rotate/resize). LANCZOS now runs on 1 byte/pixel instead of 3-4
  bytes/pixel — ~3-4× speedup, ~3× peak-memory reduction on RGBA inputs.
- `_get_profile_pixel_width()` cached per adapter (previously walked
  python-escpos profile data on every print).
- `image_processor` threshold dithering now uses a cached LUT instead
  of rebuilding a 256-entry lambda per call.
- `print_image` decodes via `process_image_from_bytes`, which drops the
  encoded `BytesIO` after `src.load()` so the encoded + decoded
  surfaces no longer coexist for the duration of the executor job.

### Changed (project / CI)

- **Migrated to typed `runtime_data` config-entry pattern.** `__init__.py`
  now exposes an `EscposRuntimeData` dataclass and `EscposConfigEntry`
  type alias; per-entry adapter and defaults live on `entry.runtime_data`
  rather than `hass.data[DOMAIN][entry_id]`. Domain-level
  service-registration flag stays in `hass.data[DOMAIN]`. Aligns with the
  HA quality-scale `runtime-data` rule. No user-facing change; all
  existing tests pass.
- **Split `docs/` into task-oriented pages** (installation, configuration,
  network, usb, bluetooth, services, automations, notifications,
  multi-printer, limitations, troubleshooting). Replaces the three
  monolithic `CONFIGURATION.md` / `EXAMPLES.md` / `TROUBLESHOOTING.md`
  files. Maps onto HA quality-scale `docs-*` rules.
- **Replaced homegrown security-scan orchestrator** in CI with native
  `bandit -lll` + `pip-audit` exit-code gates. Drops the brittle JSON
  text-grep severity matching. Workflow shrinks from 139 lines to ~70.
- Slimmed `[security]` and `[dev]` extras in `pyproject.toml` to actual
  tooling (bandit, pip-audit, pytest, mypy, ruff, pre-commit). Dropped
  `safety` entirely (never invoked by CI; `pip-audit` covers the same
  use-case).
- Dropped `[dependency-groups]` table; `[project.optional-dependencies]`
  is now the single source of truth. `uv sync --all-extras` replaces
  `uv sync --all-extras --group dev`.
- Bumped `actions/github-script@v8` → `@v9`.
- **`PARALLEL_UPDATES = 0`** declared on `notify.py`, `binary_sensor.py`,
  and `sensor.py`. Satisfies HA quality-scale `parallel-updates` rule
  (printer I/O serialization is enforced separately by adapter locks).
- **`EscposOnlineSensor`** now sets `_attr_entity_category = DIAGNOSTIC`,
  matching the battery sensor and satisfying `entity-category`.
- **`security.yml` SARIF upload fixed** — emits `bandit -f sarif` instead
  of uploading non-SARIF JSON. Previously the Security tab silently
  received nothing.
- **`dependabot-auto-sync.yml` hardened** with a same-repo guard
  (`head.repo.full_name == github.repository`) and dropped the explicit
  cross-repo checkout (defense-in-depth against the
  `pull_request_target` "pwn-request" pattern).
- **Coverage floor raised** from 70% to 80% (matches sibling
  `ha-pixelblaze`). Long-term target is silver-tier 95%.

### Tests

- New `tests/test_init.py` covers the entry-lifecycle (runtime_data
  assignment, single-entry unload tearing down services, multi-entry
  unload preserving services, adapter.stop() invocation).
- New `tests/test_diagnostics.py` covers diagnostics for network and USB
  entries, plus the defensive missing-`runtime_data` path.
- New `tests/test_device_actions.py` covers all 8 device-action types
  exercised through `async_call_action_from_config`.
- New `tests/test_services_targeting.py` covers `device_id` targeting
  (single + list), the no-target / unknown-target error paths, and the
  HomeAssistantError wrapping in print- and control-handler error paths.
- New `tests/test_adapter_lifecycle.py` covers the network-adapter
  status-check success/failure paths, listener (un)subscribe, and
  `_wrap_text` line-width handling.
- New `tests/test_options_flow_custom.py` covers the
  custom-profile / custom-codepage / custom-line-width options-flow
  branches.
- Existing `tests/test_bluetooth_battery_sensor.py` extended to cover
  `async_setup_entry` skip / create paths and `device_info`.

### Added (project / CI)

- **`quality_scale.yaml` and `manifest.json` `quality_scale: bronze`.**
  Each Bronze/Silver/Gold/Platinum rule audited and tagged
  `done`/`todo`/`exempt`. Concrete maturity signal for HACS / HA-core
  submission.
- **`info.md`** at repo root for the HACS install-dialog card.
- **`icons.json`** mapping service and entity icons centrally
  (HA quality-scale `icon-translations` rule).
- Top-level `permissions: contents: read` and `concurrency:` blocks on
  every GitHub Actions workflow. Faster CI, least-privilege tokens.

### Removed

- `tox.ini`, `.bandit`, `scripts/security_scan.py`,
  `scripts/framework_smoke_test.py`, `scripts/test_network_printer.py` —
  vestigial relative to the canonical `uv run pytest` / `bandit -lll`
  invocations.
- Stale `[tool.mypy] exclude` entries for nonexistent
  `fix_*_errors.py` scratch files.
- Stale ruff per-file-ignore for `printer.py` (now the `printer/`
  subpackage).

### Fixed (project)

- `.gitignore` now covers `htmlcov/`, `coverage.xml`, `coverage.json`,
  `.pytest_cache/`. Removed the `CLAUDE.md` ignore (committed elsewhere
  as a personal scratch file; previously dead).
- `CONTRIBUTING.md` Python version was stale at "3.11 or later"; now
  matches the `>=3.13.2` requirement in `pyproject.toml`.

### Migration notes

- **Existing `print_image` automations continue to work unchanged.** The
  `image` field still accepts the same literal strings it always did
  (URL, file path, `camera.<id>`, `image.<id>`, base64). The UI now also
  renders Jinja templates, so a literal path may appear inside a code-
  style editor when you edit the automation — that's expected; the value
  itself is unchanged.
- For a friendlier UI, switch to the focused service that matches your
  source type: `print_image_url`, `print_image_path` (new),
  `print_camera_snapshot`, or `print_image_entity`. All accept the same
  image-processing options. Migration is optional — `print_image` stays
  fully supported and remains the right choice when the source is
  computed by a template.

## [0.5.2] - 2026-05-15

### Fixed

- `notify.<printer>` entity regression that broke image attachments on
  HA 2026.2.3 transitive dependency bumps.

### Security

- Resolved Bandit warnings (low-severity findings in dev / CI scripts).
- Pinned `pip-audit` config in `pyproject.toml` for reproducible CI runs.

### Changed

- Refreshed `uv.lock` to pull in HA 2026.2.3 transitive dependency
  updates.
- Dependabot now ignores `pytest` (pinned by
  `pytest-homeassistant-custom-component`) and `dbus-fast` (pinned by
  HA core); see `.github/dependabot.yml`.
- Bumped `mypy` 1.19.1 → 2.1.0, `pre-commit` 4.5.1 → 4.6.0,
  `ruff` 0.15.1 → 0.15.13, `urllib3` 2.6.3 → 2.7.0,
  `pytest-homeassistant-custom-component` 0.13.314 → 0.13.316,
  `actions/upload-artifact` v4 → v7,
  `softprops/action-gh-release` v2 → v3.

## [0.5.1] - 2026-05-12

### Added

- HACS brand icons (`brand/icon.png`, `brand/icon@2x.png`,
  `brand/logo.png`, `brand/logo@2x.png`) so the integration renders
  with proper artwork in HACS.

### Changed

- README polish.

## [0.5.0] - 2026-05-10

### Compatibility

- **Minimum supported Home Assistant version is now 2026.2.** Earlier
  HA versions ship `dbus-fast` 2.x and miss the Bluetooth APIs this
  release relies on. Users on HA 2025.x should stay on 0.4.4.

### Security (lockfile transitives)

- Refreshed `uv.lock` to pull patched versions of dev / security
  tooling transitives:
  - `nltk` 3.9.2 → 3.9.4 (zip slip, path traversal, file overwrite,
    XSS, remote shutdown advisories)
  - `Authlib` 1.6.8 → 1.7.2 (critical JWS header injection, JWE
    RSA1_5 padding oracle, OIDC fail-open, CSRF cache)
  - `Pygments` 2.19.2 → 2.20.0 (ReDoS in GUID matching)
  - `pip` 25.3 → 26.1.1 (functionality-from-untrusted-source,
    tar/ZIP confusion)
  - `bandit` 1.9.3 → 1.9.4
- The remaining lockfile alerts (Pillow, aiohttp, cryptography,
  requests, PyOpenSSL, PyJWT, orjson, uv) are pinned by HA core's own
  manifest in 2026.2 and will resolve automatically when users update
  to HA versions where core upstreams those bumps.

### Added

- **Bluetooth Classic / RFCOMM connection type.** Adds support for paired
  Bluetooth printers (Netum, MUNBYN, POS-58 generics, Phomemo Classic
  line, etc.) alongside the existing Network and USB types. Pair-on-host
  model: the integration enumerates already-paired devices via bluez
  D-Bus when reachable, falls back to manual MAC entry, and opens raw
  `AF_BLUETOOTH` RFCOMM sockets for the data plane. Includes a new
  `bluetooth_select` / `bluetooth_manual` config-flow path, a TCP-loopback
  test seam pointed at the existing `VirtualPrinter` emulator, and
  `bt_*` error keys for actionable troubleshooting (including
  `bt_channel_refused` for wrong RFCOMM channel).
- README "Security considerations" subsection covering the cleartext
  Bluetooth Classic SPP threat model, no-PIN-pairing impersonation
  caveat, HA Container privilege trade-off, and the recommended
  `status_interval` floor for BT entries.
- `docs/TROUBLESHOOTING.md` Bluetooth section with an errno → cause →
  action table for every `bt_*` key.
- `docs/CONFIGURATION.md` Bluetooth Printers section + connection-type
  comparison table updated.
- CI: `ruff`, `mypy`, and `--cov-fail-under=85` are now enforced in
  `validate.yml`. A separate `integration-tests` job runs the
  `pytest -m integration` suite (TCP-loopback against the in-tree
  emulator — no real radio required).
- Tag-driven release workflow (`release.yml`) with version-sync
  verification.
- `scripts/check_version_sync.py` enforces that `manifest.json::version`
  matches `pyproject.toml::project.version` in CI.

### Changed

- `dbus-fast` pinned to `==4.0.4` (was `==4.0.0`); supply-chain hygiene.
- `sanitize_log_message` now redacts Bluetooth MAC addresses (preserves
  OUI for vendor lookups) and treats `address`, `mac`, `alias` as
  default sensitive fields.
- `tests/conftest.py`: unit-test stubs for `escpos*` and `usb*` modules
  use `monkeypatch.setitem` so they auto-revert at fixture teardown.
  Eliminates a session-state leak that previously required
  `_ensure_real_escpos` workarounds in integration tests.
- Bluetooth status check now defers to in-flight prints (skips the tick
  when the adapter lock is held). RFCOMM accepts only one client at a
  time, so a probe-during-print would either fail with `EBUSY` or
  interrupt the print.
- Bluetooth retry-on-error trimmed to genuinely transient errnos
  (`EBUSY`, `EIO`); `ETIMEDOUT` and `EHOSTDOWN` are no longer retried,
  cutting worst-case executor block time from 12.6 s to ~4.6 s on a
  missing printer.
- Ruff target version bumped from `py312` → `py313` (matches
  `requires-python = ">=3.13.2"`).

### Fixed

- Manifest version (`0.1.1` → `0.4.4`) re-aligned with `pyproject.toml`.
  HACS users now see the correct version.

## [0.4.4] - prior

Earlier releases — see git history.

[Unreleased]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.4.4...v0.5.0
[0.4.4]: https://github.com/cognitivegears/ha-escpos-thermal-printer/releases/tag/v0.4.4
