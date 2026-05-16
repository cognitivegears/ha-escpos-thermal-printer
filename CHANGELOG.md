# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- **Preview without printing.** New `escpos_printer.preview_image` service
  runs the full image pipeline (dither, resize, rotate, invert, mirror)
  and writes the resulting 1-bit PNG to disk *without* printing it.
  Returns `{path, width, height, slice_count}` so automations can chain
  a notification. Tune `dither`/`threshold`/`image_width` in Developer
  Tools instead of burning paper.
- **Focused convenience services.** `print_camera_snapshot`,
  `print_image_entity`, `print_image_url` — each takes only the
  relevant field with a proper UI selector (camera/image entity
  picker; URL text), funneling into the same handler as `print_image`.
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

### Changed

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

### Added

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

### Fixed

- `.gitignore` now covers `htmlcov/`, `coverage.xml`, `coverage.json`,
  `.pytest_cache/`. Removed the `CLAUDE.md` ignore (committed elsewhere
  as a personal scratch file; previously dead).
- `CONTRIBUTING.md` Python version was stale at "3.11 or later"; now
  matches the `>=3.13.2` requirement in `pyproject.toml`.

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

[Unreleased]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/releases/tag/v0.5.0
[0.4.4]: https://github.com/cognitivegears/ha-escpos-thermal-printer/releases/tag/v0.4.4
