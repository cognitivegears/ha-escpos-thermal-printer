# Network Printer Identification & DHCP Discovery — Design

Date: 2026-08-10
Status: approved

## Problem

Network printers register in the HA device registry as manufacturer "ESC/POS",
model "Network Printer" (`device.py:57-72`), and the integration has no network
discovery — users must know the printer's IP and type it in. Meanwhile the
printer itself will happily tell us what it is (Epson answers ESC/POS
`GS I` transmit-printer-ID queries over the same TCP 9100 socket we already
print through), and thermal printers announce identifiable DHCP hostnames
(vendor-documented for Epson, user-verified for Epson and Rongta).

## Scope

Two features sharing one core:

1. **`GS I` model query** — best-effort identification of the connected
   printer's maker/model during config flow, persisted to the entry and used in
   three existing surfaces.
2. **DHCP discovery** — evidence-backed hostname matchers so HA offers to set
   up a thermal printer it sees join the network.

### Explicitly out of scope (and why)

- **Zeroconf/mDNS discovery.** Research found no verifiable documentation of
  Epson TM mDNS behavior; HA core ships no printer DHCP prior art; and an
  empirical browse on the author's own network (where mDNS demonstrably
  flows — HA's `_home-assistant._tcp` was visible) showed the TM-T20II
  advertises no service at all. Add later with evidence.
- **OUI-based matchers.** Epson's 22 OUIs are shared with projectors/inkjets.
  Bixolon's `00:15:94` is the one credible candidate (single-purpose printer
  vendor) but guarantees only "Bixolon printer", not "ESC/POS receipt
  printer" — deferred until a user report confirms one working.
- **MAC-based unique IDs.** unique_id stays `host:port`; a printer whose DHCP
  lease changes IP is re-discovered as a new device. The fix (entry migration
  to MAC-keyed IDs) isn't worth it now; a DHCP reservation is the standard
  answer.
- **Querying at adapter start / device-registry refresh after setup.** The
  model can't change between setups of the same printer; existing entries pick
  the fields up on their next reconfigure.

## Feature 1: `GS I` model query

### Helper

`query_printer_id(host, port, timeout) -> dict | None` in
`_config_flow/network_helpers.py`, next to `_can_connect` (same raw-socket
style, `network_helpers.py:29-46`; no adapter needed in the flow). Runs on an
executor job.

- Opens a socket, sends `GS I 66` (0x1D 0x49 0x42 — maker name) then
  `GS I 67` (0x1D 0x49 0x43 — model name).
- Reads replies framed as `0x5F <ascii string> 0x00` with a short (~2 s) read
  timeout per reply.
- Returns `{"manufacturer": str, "model": str}` (either key may be absent if
  only one reply parsed) or `None` on timeout / garbage / connection error.
- Never raises out of the helper; never prints or changes printer state
  (transmit-ID commands are read-only). Printers that ignore the commands
  (non-Epson clones) hit the read timeout → `None` → behavior identical to
  today.

### Call site

`async_step_network` (and the reconfigure path) in
`_config_flow/network_steps.py`, immediately after `_can_connect` succeeds
(`network_steps.py:83-85`). Result stored in flow state.

### Persistence

Two new `entry.data` keys, written on create and on reconfigure:
`detected_manufacturer`, `detected_model` (const.py: `CONF_DETECTED_MANUFACTURER`,
`CONF_DETECTED_MODEL`). Absent when the query returned nothing.

### Consumers (all existing surfaces, no new UI)

1. **Device registry** — `build_device_info()` prefers
   `entry.data[detected_manufacturer/detected_model]`, falling back to the
   current `"ESC/POS"` / `_MODEL_BY_CONNECTION_TYPE` values.
2. **Profile preselect (discovery flows only)** — when discovery ran the
   query before the network form is shown, the detected model feeds the
   existing `suggest_profile(model, None, None)`
   (`capabilities/suggestions.py:26-45`) to preselect the profile dropdown
   default, exactly as Bluetooth does with the advertised name
   (`bluetooth_steps.py:55-68`). Preselect only — never auto-commit. In the
   *manual* flow the profile dropdown is on the same form as the host field,
   so the query (which runs on submit) cannot preselect it — manual entries
   get the detected fields persisted but keep their chosen profile.
3. **Calibrate share link** — the free-text model field on the calibration
   summary (`calibration_steps.py:537-538`) defaults to
   `entry.data[detected_model]` when present, instead of the empty
   placeholder.

## Feature 2: DHCP discovery

### Manifest matchers (evidence-only)

```json
"dhcp": [
  {"hostname": "tm-*"},
  {"hostname": "rongta_*"}
]
```

- `tm-*`: Epson FAQ KA-01071 documents the default network name rule as
  "printer product name + last 6 MAC hex digits", with literal examples
  `TM-T88VI-C3FE21` and `TM-m30-FED95E`; user-verified `TM-T20II-628E52`.
  Every Epson receipt printer's product name starts with `TM-`.
- `rongta_*`: user-verified `Rongta_RP820`; generalized to the brand prefix
  because anything announcing `rongta_*` is a Rongta device and Rongta makes
  only printers.

Known Epson caveat (same FAQ): some older boards (UB-R03/R04, some TM-T20II
variants) announce no hostname — those simply aren't discovered; manual setup
still works.

### Flow

New `_config_flow/discovery_steps.py` mixin (mirrors the file-per-transport
layout) added to `EscposConfigFlow`:

`async_step_dhcp(discovery_info)`:

1. `unique_id = f"{ip}:9100"`; `_abort_if_unique_id_configured()` — already-set-up
   printers and in-progress flows abort silently.
2. Executor probe `_can_connect(ip, 9100, short_timeout)` — a hostname match
   that isn't listening on 9100 aborts silently (`abort` reason
   `cannot_connect`), so matcher false positives never nag the user.
3. `query_printer_id(...)` — best-effort, result carried into the flow.
4. Hand off to the existing `async_step_network` form with host prefilled.
   The network form is the confirmation step — no new confirm UI; everything
   downstream (profile preselect, codepage, calibrate) is reused unchanged.
   The network step's strings.json description stays static (it is shared
   with the manual flow, which supplies no placeholders); the discovery card
   title carries the identification instead.

Discovery card title uses the detected model when available ("TM-T20II at
192.168.10.157"), else the DHCP hostname.

## Strings & docs

- `strings.json` + `translations/en.json`: discovery step title/description
  placeholders, abort reasons (reuse existing `cannot_connect` /
  `already_configured` where possible).
- CHANGELOG `[Unreleased]`: one entry per feature.
- README: short "Discovery" note (what gets auto-discovered, what doesn't and
  why manual setup is always available).

## Testing

- **Parser unit tests** for `query_printer_id` framing: happy path, no reply
  (timeout), garbage bytes, missing NUL terminator, maker-only reply,
  connection refused. Socket mocked; follow `tests/test_config_flow.py`'s
  `_can_connect` patch style (`tests/test_config_flow.py:25`).
- **Config flow**: network step persists detected fields; reconfigure
  refreshes them; profile preselect honors the detected model; query returning
  `None` leaves behavior unchanged.
- **Discovery flow**: dhcp step happy path (→ prefilled network form →
  entry created with detected fields), abort on already-configured, abort on
  probe failure, duplicate in-progress flow.
- **Device info**: `tests/test_device_info.py` extended — detected fields
  preferred, fallback intact.
- **Calibration**: model field prefill from `entry.data`.
