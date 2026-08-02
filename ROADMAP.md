# Roadmap

Post-1.0 improvements, ranked by value. Sourced from the pre-1.0 review
(2026-08-02): a code-correctness pass, a python-escpos API gap analysis, and an
entity-coverage analysis against HA platform conventions.

## Planned

### 1. Button entities: Feed, Cut, Calibration print

The dashboard staples for a receipt printer — tap to advance paper before
tearing, tap to cut, tap to print a test sheet when debugging alignment.
Everything needed already exists: `adapter.feed()` / `adapter.cut()`
(`printer/control_operations.py`) and the `calibration_print` service. Roughly
three `ButtonEntity` subclasses reusing `build_device_info()`, plus `"button"`
in `PLATFORMS`, icons, and strings. Beep as a fourth button is optional.

### 2. Cash drawer service

`open_cash_drawer` (python-escpos `cashdraw`, pin 2/5) plus a matching device
action. The one classic POS capability entirely absent from the integration.

### 3. Text styling: `invert`, `density`, `font` on `print_text` / `print_message`

The library's `set()` already accepts white-on-black (`invert`), print darkness
0–8 (`density`), and font A/B (`font`, B = smaller/more columns); the adapter
just doesn't surface them. Additive schema fields alongside the existing
`bold`/`underline`/`width`/`height`.

### 4. Cover-open / error binary_sensor

Cover-open is the second-most-common printer fault after paper-out, and the
DLE EOT n=2 transmit-status query works on the same transports as the existing
paper sensor (network + USB). Implementation notes:

- Fold the query into the existing 5-minute paper poll's connection
  (`base_adapter.get_paper_status()`) — do not open a second connection.
- Treat a zero-length response as *unknown*, never "OK": python-escpos
  interprets an empty read as a healthy status, so a silent printer would
  otherwise report a false all-clear.

### 5. Last-print timestamp sensor

`SensorDeviceClass.TIMESTAMP` enabling "no receipt printed today" automations.
Needs a new `_last_print` field set only in the print paths — the existing
`_last_ok` is also updated by status probes, so it means "last successful
operation", not "last print".

### 6. Smaller items

- **`hw("INIT")` reset service** — cheap recovery path for a wedged printer.
- **Native QR rendering** (`qr(native=True)`) — faster and sharper than the
  image path, but needs a fallback since not all printers support it.
- **ESC/POS `line_spacing()`** — compact receipts. Note the name collides with
  the PIL renderer's `line_spacing` field on `print_text_image`; pick a
  distinct service field name.
- **Push updates for the image-print sensor** — it currently polls on a
  5-minute interval despite the adapter having a listener mechanism.
- **`_last_error_errno` in the Online sensor's attributes** — already tracked
  by the adapters and exposed in diagnostics, just not on the entity.

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
