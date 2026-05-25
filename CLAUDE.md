# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Home Assistant custom integration for ESC/POS thermal receipt printers. Supports both **network (TCP/IP)** and **USB** connected printers. Enables printing text, QR codes, barcodes, images, and control commands (feed, cut, beep) through HA services and automations.

## Common Commands

```bash
# Install dependencies (use uv)
uv sync --all-extras --group dev

# Run tests (excludes integration tests by default)
uv run pytest -q

# Run a single test file
uv run pytest tests/test_services_text.py -v

# Run integration tests specifically
uv run pytest -m integration

# Linting and type checking
uv run ruff check .
uv run mypy

# Pre-commit (runs automatically on commit)
pre-commit run --all-files

# Check requirements sync between pyproject.toml and manifest.json
python scripts/check_requirements_sync.py

# Auto-fix manifest.json from pyproject.toml
python scripts/sync_manifest_requirements.py

# Run local Home Assistant with integration mounted (http://localhost:8123)
docker compose up -d
docker compose down  # to stop
```

## Architecture

### Core Components (`custom_components/escpos_printer/`)

- **Entry point** — `__init__.py` initialises `EscposRuntimeData` on
  `entry.runtime_data`, forwards platforms, and delegates service
  registration to `services/registration.py::async_setup_services`
  (21 services across text / text-effects / image / preview / control
  / calibration / barcode families).

- **`printer/`** — adapter subpackage. `base_adapter.py` defines the
  abstract adapter and composes four operation mixins
  (`print_operations`, `image_operations`, `barcode_operations`,
  `control_operations`) through the shared `_PrinterHost` Protocol in
  `_host.py`. Three transports: `network_adapter.py`, `usb_adapter.py`,
  `bluetooth_adapter.py` (+ `_escpos_bluetooth.py` for the raw RFCOMM
  python-escpos subclass and `bluetooth_transport.py` for the socket
  layer). `factory.py` / `config.py` instantiate the right adapter per
  config type. `image_processor.py` handles dither / threshold / slice;
  `mapping_utils.py` normalises codepage / profile lookups.

- **`text_effects/`** — pure-Python layout subpackage (no HA, no
  printer imports). `box.py` / `table.py` for character-cell layouts;
  `font_render.py` for PIL bitmap rendering with bundled DejaVu fonts;
  `borders.py` + `width.py` for the glyph palette and visual-column
  measurement (using `wcwidth`).

- **`services/`** — handler subpackage. `registration.py` registers
  all 21 services and forwards `supports_response=ONLY` on the three
  preview services. `schemas.py` defines voluptuous schemas (sharing
  `_image_option_fragment()` across the six image services).
  `print_handlers.py` + `control_handlers.py` implement service bodies,
  all routed through the `_for_each_target` helper in
  `_handler_utils.py` for consistent per-target loop + error wrapping
  + sanitised exception messages. `target_resolution.py` resolves
  `device_id` selectors to config entries.

- **`image_sources.py`** — HA-aware fetcher. Resolves any
  `print_image` source string (data URI, camera/image entity, HTTP
  URL, local file) into `(bytes, content_type)`. Builds a per-request
  `aiohttp` session pinned via `_StaticResolver` so DNS rebinding
  cannot swap public → private between validation and fetch.

- **`security.py`** — single source of truth for `MAX_*` bounds, input
  validation, log sanitisation, and the `O_NOFOLLOW` read/write
  primitives (`open_local_image_no_follow`, `open_local_font_no_follow`,
  `write_file_no_follow`) shared by image / font / preview paths.
  `validate_font_path_with_fonts_dir` centralises the `<config>/fonts/`
  narrowed-trust decision.

- **`_config_flow/`** — UI config-flow subpackage. `main_flow.py` is
  the top-level `ConfigFlow`; per-transport step modules
  (`network_steps.py`, `usb_steps.py`, `bluetooth_steps.py`) +
  shared helpers (`network_helpers.py`, `usb_helpers.py`,
  `bluetooth_helpers.py`). Settings + custom-profile +
  options-flow paths live in `settings_steps.py` / `options_flow.py`.
  `import_steps.py` handles legacy YAML import.

- **Platforms** — `notify.py` (entity-based notify), `binary_sensor.py`
  (reachability), `sensor.py` (image-pipeline diagnostics + BT
  battery), `diagnostics.py` (download-diagnostics with
  `CONF_HOST` redaction).

- **Other** — `bluez.py` (paired-device discovery via D-Bus),
  `text_utils/` (codepage transcoder), `capabilities/` (profile
  capability lookups), `device_action/` (device-automation actions),
  `fonts/` (bundled DejaVu trio + LICENSE), `quality_scale.yaml`,
  `icons.json`, `const.py` (domain name, service names, attribute
  keys, defaults, USB / Bluetooth constants, `THERMAL_PRINTER_VIDS`).

### Testing (`tests/`)

- Unit tests use `pytest-homeassistant-custom-component` with async mode auto-enabled.
- Integration tests in `tests/integration_tests/` include a virtual printer emulator, mock data generators, and scenario tests.
- Tests marked `@pytest.mark.integration` require HA runtime and are excluded by default.
- Set `ESC_POS_DISABLE_PLATFORMS=1` to skip platform forwarding in unit tests.

### Dependency Management

- **pyproject.toml** is source of truth for dependencies.
- **manifest.json** must mirror runtime deps (synced via `scripts/sync_manifest_requirements.py`).
- Renovate auto-updates pyproject.toml; a post-upgrade task syncs manifest.json.
- Pre-commit hooks block commits if files drift.
- **Always use pinned versions** (`==`) for all dependencies, not ranges (`>=`). This ensures reproducible builds and better security.
- **`pytest` is pinned by `pytest-homeassistant-custom-component`** (currently `pytest==9.0.0`). Dependabot is configured to ignore standalone `pytest` bumps (see `.github/dependabot.yml`). When upgrading the HA test harness (`pytest-homeassistant-custom-component`), check whether the new version pins a different `pytest` and bump `pytest` in `pyproject.toml` to match. If upstream ever loosens the pin, remove the `pytest` ignore rule from `dependabot.yml`.
- **`dbus-fast` is pinned by Home Assistant core** (`package_constraints.txt`) and the HA bluetooth integration manifest. Bumping ahead of HA breaks installs. Dependabot is configured to ignore `dbus-fast` (see `.github/dependabot.yml`). When upgrading HA itself, check HA's current `dbus-fast` pin and bump it in `pyproject.toml` + `manifest.json` to match.
- **`Pillow` is pinned to match Home Assistant core's bundled Pillow** (HA ships its own at runtime; `manifest.json` carries a range so we don't fight HA's pin). Dependabot is configured to ignore standalone `pillow` bumps (see `.github/dependabot.yml`). When upgrading HA, check HA core's current Pillow pin and bump `Pillow` in `pyproject.toml` to match.
- **`respx` is pinned by `pytest-homeassistant-custom-component`** (currently `respx==0.22.0`). Dependabot is configured to ignore standalone `respx` bumps (see `.github/dependabot.yml`). When upgrading the HA test harness, check whether the new version pins a different `respx` and bump it in `pyproject.toml` to match.
- **After HA version bumps, re-check Dependabot security alerts** (`https://github.com/cognitivegears/ha-escpos-thermal-printer/security/dependabot`). Most open alerts are against the HA-pinned packages above — direct (`pyproject.toml` Pillow) or `uv.lock` transitives (aiohttp, pyOpenSSL, PyJWT, orjson, requests, uv, cryptography, etc.). They only affect dev/CI environments — end users install via `manifest.json` — and auto-clear when HA releases a version with patched pins. After a HA bump (i.e. once `pytest-homeassistant-custom-component` points to the new HA), run `uv lock --upgrade` and verify which alerts close.
- **The `ignore:` block in `dependabot.yml` only suppresses *version* updates** — it does not suppress *security* updates (which trigger the Dependabot Updates worker independently and will fail noisily when the bump conflicts with an HA pin). For HA-pinned packages, dismiss the security alert as `tolerable_risk` with a note pointing at the HA pin; the alert will re-surface if a new advisory lands against the still-current pinned version.

## Key Patterns

- All printer I/O runs on executor threads via `hass.async_add_executor_job()`.
- Printer adapters use an `asyncio.Lock` to serialize print operations.
- Late import of `escpos.printer.Network` and `escpos.printer.Usb` avoids import errors during HA startup.
- Security validation happens before any printer operation (see `security.py`).
- **Network printers:** Status checking uses non-blocking TCP probes.
- **USB printers:** Status checking uses USB device enumeration via `usb.core.find()`. Keepalive is always disabled (reconnect-per-operation model).
- USB printers are auto-discovered by matching vendor IDs in `THERMAL_PRINTER_VIDS`.
- Factory pattern (`create_printer_adapter()`) instantiates the correct adapter based on connection type.
- Unique IDs: Network uses `host:port`, USB uses `usb:VID:PID[:serial]`.

### Image services: field-set parity invariant

All six image-printing services (`print_image`, `print_image_url`, `print_image_path`, `print_camera_snapshot`, `print_image_entity`, `preview_image`) share a single voluptuous option-set mixin (`_image_option_fragment()` in `services/schemas.py`) and a single backend dispatcher (`_dispatch_print_image()` in `services/print_handlers.py`). Their `services.yaml` field definitions are therefore duplicated metadata — when adding/renaming/removing an option, update all six blocks in lockstep.

`tests/test_services_yaml_schema.py::test_image_services_share_common_field_metadata` enforces the invariant: every common field's `name`, `description`, and `selector` must match `print_image`'s. The `default:` *may* legitimately differ on `auto_resize`, `autocontrast`, and `feed` (each focused service picks its own friendly default) — those keys are listed in `_DEFAULT_MAY_VARY` in the test. Any drift outside that allowlist is a test failure.

`test_image_services_no_truncated_descriptions` is the regression guard for the YAML `#` comment-truncation class of bug (an unquoted plain-scalar description containing `#` silently terminated mid-sentence in the rendered HA tooltip). Quote any single-line description that contains `#`, or use a `>` folded scalar.

`preview_image` deliberately omits the printer-communication knobs (`high_density`, `impl`, `fragment_height`, `chunk_delay_ms`, `center`, `cut`, `feed`) because they have no effect on the PNG written to disk. The schema still accepts them so programmatic callers don't break; `handle_preview_image()` logs a debug line when they're passed.

### Per-service source-type validators

`PRINT_IMAGE_URL_SCHEMA` and `PRINT_IMAGE_PATH_SCHEMA` use `_url_only` / `_local_path_only` prefix validators (in `services/schemas.py`) so the schema enforces what the service description advertises. Without these guards, the underlying `_classify()` would happily route a wrong-shape value through a different resolver — downstream defenses (SSRF, allowlist, O_NOFOLLOW, entity ACL) still apply, but the schema-level guard makes the per-service contract explicit and means error messages line up with the service the user invoked.

### Text-effects layout helpers

`handle_print_box` / `handle_preview_box` and `handle_print_table` / `handle_preview_table` share `_render_box_layout()` / `_render_table_layout()` (in `services/print_handlers.py`) for the sanitise → render → resolve-codepage steps. The `print_*` handlers transcode + dispatch through `adapter.print_text`; the `preview_*` handlers transcode + write to a `.txt` file. Mirrors the `_dispatch_print_image()` pattern for the image services — change a layout step in one place, both consumers stay in sync.

### Font path trust

`print_text_image.font_path` accepts files under `<config>/fonts/` (auto-created on integration setup) *or* anywhere in HA's `allowlist_external_dirs`. The integration narrowly trusts that one directory to remove the "I dropped a TTF in /config/fonts/ and got an allowlist error" friction. Single entrypoint: `security.validate_font_path_with_fonts_dir(raw_path, hass)` runs the extension / size / symlink / regular-file checks via `validate_font_path()`, then accepts the resolved path if it lives in `allowlist_external_dirs` or under `<config>/fonts/`. Centralising the trust decision in `security.py` keeps the path-validation policy in one auditable place.

### Blueprints

The `blueprints/` directory ships HA scripts and automations. Validated by `scripts/validate_blueprints.py` (YAML structural check tolerant of the `!input` tag); enforced by `tests/test_blueprints_yaml.py` and the `validate-blueprints` pre-commit hook. Each file lives under a directory matching its `blueprint.domain` (`script` or `automation`) — the validator catches drift.
