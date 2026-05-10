# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
