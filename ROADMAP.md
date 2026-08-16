# Roadmap

Post-1.0 improvements, ranked by value. Sourced from the pre-1.0 review
(2026-08-02): a code-correctness pass, a python-escpos API gap analysis, and an
entity-coverage analysis against HA platform conventions.

## Planned

### 1. Button entities: Feed, Cut, Beep, Sample print — shipped

Device page buttons ship: Feed, Cut, Beep, and Sample test print (a one-tap
demo receipt with the integration logo, styled text, a table, and a QR
code), backed by `adapter.feed()` / `adapter.cut()` / `adapter.beep()` and a
new `sample_print.py` composer built on `batch_connection()`. A
calibration-sheet button was deliberately **not** added — the new Settings →
Repairs suggestion (below) already points users at the calibration wizard,
and the `calibration_print` service remains for the dither/threshold test
sheet.

New printers also get a fixable Settings → Repairs issue
("Printer not yet calibrated") that opens the calibration wizard directly,
so it's discoverable without hunting through the integration's Configure
menu. See [Calibration wizard](docs/calibration.md).

### 2. Cash drawer service — and the drawer-kick port as a "geek port"

**Core functionality**: `open_cash_drawer` (python-escpos `cashdraw`, pin 2/5)
plus a matching device action, and optionally a button entity alongside the
shipped Feed/Cut/Beep/Sample buttons (item 1). The one classic POS capability
entirely absent from the integration.

**Investigation: general-purpose I/O.** The drawer-kick connector (RJ11/RJ12)
is electrically more than a cash-drawer plug, which makes it interesting as a
cheap "geek port" for HA users without a drawer:

- *Output*: `ESC p m t1 t2` fires a timed 24 V pulse on pin 2 or pin 5 with
  configurable on/off duration — enough to drive a relay module, door strike,
  or buzzer. Pulse-only, not level-hold, so it maps to an HA momentary
  switch/button rather than a real GPIO line.
- *Input*: the real-time status query `DLE EOT n=1` reports the drawer
  kick-out connector pin 3 level, giving one readable sense line — a
  binary_sensor for a door contact or any dry-contact switch, piggybacking on
  the same poll loop as the existing paper sensor.

Open questions for the investigation: which transports support the status
read (network + USB likely, Bluetooth/serial to verify), per-model behavior of
pulse timing limits, how to present this in the UI without confusing
cash-drawer users (probably an "advanced" config option that renames the
entities), and safety copy warning that pin voltage is 12/24 V solenoid drive,
not logic-level.

### 3. Text styling: `invert`, `density`, `font` on `print_text` / `print_message` — shipped

`invert` (white-on-black), `density` (0–8), and `font` (A/B) are now additive
schema fields on `print_text`, `print_text_utf8`, and `print_message`, next to
the existing `bold`/`underline`/`width`/`height`, applied through the
library's `set()` and scoped so `invert` doesn't leak into a following QR,
barcode, or image print on the same connection.

### 4. Cover-open / error binary_sensor — shipped

A `binary_sensor.<printer>_cover_open` entity reports a stuck-open cover for
network and USB printers, backed by the DLE EOT n=2 real-time query. It folds
into the existing paper sensor's connection (`base_adapter.get_paper_status()`)
behind a shared 60-second freshness guard, so the two pollers share one round
trip instead of opening a second connection. A zero-length or non-conformant
response (missing the real-time-status byte's fixed bits) is treated as
*unknown*, never "OK"/"closed" — python-escpos's own paper-status default
would otherwise report a false all-clear on a printer that ignores or
garbles the query.

### 5. Last-print timestamp sensor — shipped

`sensor.<printer>_last_print` (`SensorDeviceClass.TIMESTAMP`) enables "no
receipt printed today" automations. Distinct from the Online sensor's
`last_ok`, which status probes also refresh — this is set only by the print
paths (text, QR, barcode, image, batch), and stays unknown until the first
print after a restart (not persisted).

### 6. Print confirmation for network printers

Today a TCP send to port 9100 proves bytes left the NIC, not that paper moved —
a link that drops mid-stream (e.g. a flaky WiFi bridge) looks like success.
Neither variant exists in python-escpos (it only implements the DLE EOT
real-time queries, which answer from the receive buffer and don't confirm
printing), so both need raw command + response parsing in the adapter:

- **Epson (`GS ( H` process ID response)**: queue a 4-byte ID after the job;
  the printer echoes it back only once everything before it has been
  processed. Supported by TM-series printers (incl. TM-T20II). Reuses the
  send-then-read round trip the paper sensor already does.
- **Star (ETB counter in the ASB status block)**: append an ETB byte (0x17)
  after the job, read the ASB ETB counter before and poll after; it only
  advances when the printer physically feeds past the marker. Counter
  position/step varies by model (mC-Print3: byte 7, +2 per ETB), so keep the
  parsing per-profile. Only relevant if Star ASB support lands.

**Retry policy (applies to any confirmation work)**: delivered-but-unconfirmed
is not failed. If the job was sent but the confirmation read dies, report
"unconfirmed" and do **not** retry — the print likely succeeded and a blind
retry double-prints. Retry only on positive evidence the job did not go
through, and keep everything after the committed send exception-safe so it
cannot re-fire.

### 7. Smaller items

- **`hw("INIT")` reset service**: cheap recovery path for a wedged printer.
- **Native QR rendering** (`qr(native=True)`): faster and sharper than the
  image path, but needs a fallback since not all printers support it.
- **ESC/POS `line_spacing()`**: compact receipts. Note the name collides with
  the PIL renderer's `line_spacing` field on `print_text_image`; pick a
  distinct service field name.
- **Push updates for the image-print sensor**: it currently polls on a
  5-minute interval despite the adapter having a listener mechanism.
- **`_last_error_errno` in the Online sensor's attributes**: already tracked
  by the adapters and exposed in diagnostics, just not on the entity.

## Planned for 2.0.0 (breaking)

- **Remove the implicit broadcast-when-no-target fallback**: service calls
  will require an explicit target (`device_id` or an entity/area/floor/label
  target) or `broadcast: true`. Deprecated since 1.2.0; a warning has been
  logged for this case since multi-printer support was added.

## Considered and rejected

| Idea | Why not |
| --- | --- |
| `number`/`select` entities for codepage/profile/cut defaults | Duplicates the options flow, which already reloads on change; HA convention keeps setup-time config in options. |
| Keepalive switch entity | Same reasoning as above. |
| "Printing" state binary_sensor | The op lock is held for one job and there is no queue; the state would flicker and drive nothing. Revisit only if multi-minute Bluetooth image jobs warrant a progress indicator. |
| Job-count sensor for all print types | No queue, no backlog, nothing to automate on. |
| Device triggers for paper-out | A state trigger on the existing paper enum sensor already covers it. |
| `DataUpdateCoordinator` rewrite | Current push-on-outcome + independent polls design is fine; the coordinator's real win (one connection for all polled reads) is achieved by item 4 with a far smaller diff. |
| Pole displays, slip/cheque station, `block_text`, `panel_buttons` | Niche python-escpos features irrelevant to thermal-receipt users. |
