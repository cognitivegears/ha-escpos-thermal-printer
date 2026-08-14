# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [1.1.0] - 2026-08-14

### Added

- Epson TM-T70 and TM-T70II are recognized as compatible models (aliased
  to the bundled TM-T88V profile, whose 512px/180dpi/42-56-column class
  and codepage table match both). Epson TM-m30, TM-m30II, and TM-m30III
  are now supported via a built-in `TM-m30III` profile carried from the
  upstream escpos-printer-db printer database — newer than the one
  python-escpos 3.1 ships, so it isn't available there yet. (The TM-m30II
  TRG confirms an exact geometry and font match: 576 dots, 48/57/64
  columns.)
- Rongta RP80 and RP328 are recognized as compatible models, mapped to
  the built-in `RP820` profile: RP328's vendor spec (72mm/203dpi = 576
  dots, 48/64 columns) and the official RP80 command-set manual (same
  font table and Epson-standard codepage layout as the hardware-verified
  RP850P) both match the RP820 class.
- Bixolon SRP-350III (180dpi/512-dot class, aliased to TM-T88V) and its
  203dpi sibling SRP-352III (576-dot class, aliased to TM-T20II) are
  recognized as compatible models, per Bixolon's official user's manual.
- Citizen CT-S801/CT-S851 and their II revisions are recognized as
  compatible models (aliased to TM-T20II): Citizen's manuals confirm the
  203dpi/576-dot default on 80mm paper, and its command reference
  accepts the Epson-standard codepage numbers. Units memory-switched to
  83mm/640-dot stock should recalibrate width.
- Epson TM-m10 (58mm compact) is supported via a built-in profile with
  geometry from Epson's own technical reference (420 dots at 203dpi,
  35/42/46 columns — a class no bundled profile covers). Its codepage
  table is borrowed from the TM-m30 family (Epson gates the per-model
  table behind an NDA) — run the calibration wizard to verify encodings
  on real hardware.
- The Bluetooth device picker now also recognizes printers by their cached
  Serial Port Profile (SPP) record, not just the imaging device class —
  cheap printers that don't advertise the imaging class show up in the
  filtered dropdown instead of hiding behind "Show all".
- Adding a printer without a real profile ("Generic (no profile)" or the
  generic `default` profile) now shows a tip on the success screen
  pointing at the calibration wizard (Configure → Calibrate printer).
- Network printers are identified at setup via ESC/POS `GS I` queries: the
  device page shows the real manufacturer/model (e.g. EPSON TM-T20II), the
  calibration share link prefills the model name, and the detected
  manufacturer/model are included in diagnostics downloads. Printers that
  don't answer (most clones) behave exactly as before. Existing network
  printer entries pick up the detected model the next time they are
  reconfigured.
- DHCP discovery for network thermal printers: Home Assistant now offers to
  set up Epson TM-series (`tm-*`) and Rongta (`rongta_*`) printers it sees
  join the network. Candidates are probed on port 9100 first, so matches
  that aren't printers are ignored silently; `tm-*` hostnames additionally
  require a real `GS I` answer, since port 9100 is also Prometheus
  node_exporter's default. Discovered setups preselect
  the matching printer profile when one is known. Discovered entries are
  additionally tracked by MAC address, so a DHCP lease change updates the
  existing entry's host in place instead of offering a duplicate.
- Network printer entries are now titled by their detected model (e.g.
  "TM-T20II (192.168.1.50:9100)") instead of the bare address. Manual
  renames are still never overwritten when a lease change or reconfigure
  updates the address.
- Discovery now retries the port-9100 probe for up to a minute, so a
  printer whose network stack is still booting when its DHCP lease lands
  no longer misses its discovery card until the next lease renewal.

- Per-entry "Paper width in pixels" override — fixes image sizing for
  printers whose profile lacks a width (previously a Repairs issue with
  no user-side fix).
- USB config flow now preselects a suggested profile from the device's
  USB descriptor or a curated VID:PID list.
- Bluetooth config flow now preselects a suggested profile from the
  paired device's advertised name (same preselect-only matching as USB).
- Clone/equivalent model aliases (e.g. Citizen CT-S601II → CT-S651,
  ZJ-5890 → POS-5890) accepted in the custom profile field.
- 16 more researched clone/equivalent model aliases: Epson TM-T20III/
  TM-T20X/TM-T82II/TM-T82III/TM-T88VI/TM-T88VII, Xprinter XP-58IIH/
  XP-80C/XP-N160II/XP-T80A, Zjiang ZJ-5802, HOIN HOP-E58, Goojprt
  PT-210, Netum NT-1809DD, Sunmi V1/T2, Rongta RP850P (hardware-verified).
- Aliased models now appear directly in the profile dropdown as
  "Model (compatible)" entries, so users can find a rebadged printer
  without knowing the custom-profile field exists.
- Per-entry "Image printing implementation" option (Auto/Raster/Column/
  Graphics) with plain-language guidance.
- Printer calibration wizard (Settings → Configure → "Calibrate printer"):
  prints guided test pages to dial in image implementation, paper width,
  columns, and (optionally) codepage, then saves them for the entry — and
  offers a prefilled GitHub issue link with the full measured support matrix
  and a draft printer profile for contributing back.
- Calibration wizard now shows a confirmation screen (paper cost,
  ~15–20 cm; make sure paper is loaded) before printing anything, and
  tests a fifth, wider paper-width bar (832px, for 100/112mm heads).
- Diagnostics downloads now include `width_pixels` and `impl` per entry,
  plus the runtime-resolved paper width, default image implementation,
  and no-image-support flag, for triage.

### Changed

- The calibration wizard's "characters per line" step now uses a typed
  number box (16–96) instead of a 0–96 slider, and skipping is an
  explicit "Skip this step" action instead of the magic value 0. The
  user is transcribing a count they just read off the paper, so a
  slider was the wrong control, and its 0 default made the skip
  convention easy to trigger by accident. Continuing with the count
  left empty now asks for a value or an explicit skip.

- Calibration summary step simplified: the confusing "Update share link
  with my model" action is gone. Enter the model (optional), Save or
  Discard — the personalized GitHub share link now appears on the
  final confirmation screen after saving (and still in a notification).
- Calibration test pages feed two extra blank lines after each test, so
  the results clear the tear bar without a manual feed.

- **Behavioral:** image implementation now defaults from the printer
  profile (raster, or column for column-only printers) instead of
  always raster; reliability presets no longer force `bitImageRaster`.
  Explicit `impl` in service calls is unaffected.
- Profile dropdown's "Auto-detect (Default)" renamed to "Generic (no
  profile)" — it never detected anything.
- Printing an image on a profile that declares no image support now
  logs a warning (the print is still attempted).
- `calibration_print` service renamed in the UI to "Print dither test
  sheet" to avoid confusion with the calibration wizard.
- Calibration wizard's paper-width bars are now drawn as an outline
  instead of a solid fill — same measurement, a fraction of the ink
  (kinder to the print head on battery-powered Bluetooth printers).

### Fixed

- The encoding calibration step no longer offers ISO-8859-1 when no
  printer profile is configured (or the configured name is unknown). In
  those cases the printer runs python-escpos's default profile, which
  cannot switch to ISO-8859-1: the sample line silently printed under the
  previous line's codepage, looked correct on paper, and the stored
  codepage then failed on every later print. Candidates are now filtered
  against the profile the printer actually runs with.
- The width-bars calibration step no longer reports "Printing the test
  page failed" on printers whose profile declares a pixel width.
  python-escpos refuses to send images wider than the profile's
  `media.width.pixels`, so the bars beyond that width (640/832 on a
  576-dot TM-T20II) raised an error that aborted the page. The width
  bars now bypass that profile check for the duration of the send —
  wider-than-true-width bars are the measurement (hardware clips them
  to the same length), and the bypass also makes an under-declared
  profile width detectable instead of silently "confirmed". Each bar
  is additionally attempted independently, so a printer rejecting one
  bar can't abort the rest; the step only errors if no bar prints.
- Calibration test pages now print each page over a single printer
  connection instead of one connection per label/pattern. With the
  reconnect-per-operation model, printers that accept a new connection
  before draining the previous one could print the fragments out of
  order (seen on TM-T20II: TEST 1/3/2 labels shuffled, garbled pattern
  rows, and the trailing feed landing mid-page).
- The width calibration step now asks the user to spot an intact
  right-side border on the widest of several labeled boxes, instead of
  comparing two bars' lengths by eye. The old length-comparison judgment
  misread a real printer (512px vs. its true 576px, an 11% difference) on
  faint thermal ink, storing a too-narrow width. Labels now print as a
  separate text line above each box rather than baked into the image, and
  the candidate widths gained a finer step (384, 512, 546, 576, 640, 832
  — 546 covers the Epson 42-column-mode width class).
- The "Characters per line" field in setup and options is now a combobox:
  pick a preset or type a custom number directly. Previously a
  "Custom (enter columns)..." choice promised an entry box that only
  appeared on a follow-up screen after submitting, which read as "no box
  to enter a value". The legacy two-step path still works.
- Rongta RP850P/RP820 printers (the network identity RP850P hardware
  announces) now use a built-in `RP820` profile with the firmware's
  real Epson-style codepage numbering, and are recognized as a
  compatible model so discovered Rongta printers preselect it. They
  were previously aliased to the bundled `NT-80-V-UL` profile, whose
  codepage table used non-standard ESC t values that don't exist in
  this firmware, garbling every calibration codepage except CP850.
  The new profile declares the hardware-probed 48-column DIP (SW-5)
  geometry — 576px raster width, 48/64 text columns — and documents
  that the 42-column position switches the whole geometry to
  512px/42/56; recalibrate after flipping the switch.
- Every bundled profile's codepage table is now deduped at runtime: some
  profiles map a codepage name to both a low index and a duplicate index
  >= 48, and since python-escpos always emits the last-registered index,
  affected printers got the >= 48 one — unreachable on clone firmware's
  0-47 ESC t table, garbling that codepage. Only the >= 48 duplicate is
  dropped (never the low one), so this only ever affects codepage names
  that had a working low-index duplicate to fall back to; the surviving
  index isn't guaranteed to be Epson's own standard number for that
  codepage (e.g. `NT-80-V-UL`'s CP864 dedupes to 28, in-range but not
  Epson's 37) — only that it now falls inside the range clone firmware
  actually implements. Codepage names that only ever had a single index
  >= 48 are unaffected and remain unverified on clone hardware. This
  fixes garbled non-CP850 codepages on every model aliased to `NT-80-V-UL`
  (Xprinter XP-80C/XP-N160II/XP-T80A, Sunmi T2) and `POS-5890`/`NT-5890K`
  (Zjiang ZJ-5890/ZJ-5890K/POS-5890K/ZJ-5802, Xprinter XP-58IIH, HOIN
  HOP-E58, Goojprt PT-210, Netum NT-1809DD). `NT-80-V-UL`'s Font A/B
  column counts (previously 12/9, actually glyph dot widths mistakenly
  entered as columns) are also corrected to 48/64, fixing implausible
  line-width options on the same models. All three fixes mirror
  corrections already reported upstream to escpos-printer-db.

- Text wrapping no longer strips a trailing newline, so calibration
  test-page labels flush before each pattern instead of being dropped
  into or merged with the following image (seen on Ronga RP850P).
- Clone printers announcing a brand hostname (e.g. `rongta_*`) no longer
  masquerade as their emulation target in discovery/device info, even
  when their firmware's `GS I` reply claims to be a different brand.
- Implausible font column counts from the profile database (an upstream
  data bug encoding font dot widths as column counts) no longer surface
  as characters-per-line choices.

- Every calibration test page now prints a title ("= CALIBRATE 1/4: IMAGE
  MODE ="), a one-line instruction, and trailing feed lines so the steps are
  self-explanatory and visually separated on the roll.
- Calibration codepage lines now print their codepage name (e.g. "1 CP858:")
  so the paper matches the on-screen checkboxes directly.
- Calibration ruler readability: full numbers (10, 20, 30...) embedded in the
  ruler instead of single tens digits and pipe marks, plus a printed
  instruction line — read the last complete number on the first line and add
  the dots after it.
- Calibration width bars: the size label inside each bar was printed with an
  ~11px bitmap font (about 1.4mm on paper — unreadable); bars are now taller
  with a 30px label.
- Calibration wizard test labels ("TEST 1/2/3") and codepage sample lines now
  end with a newline — without it, ESC/POS printers never flushed the text
  buffer, so raster printers dropped the label and column printers merged it
  into the pattern (seen on a Rongta RP850P).

- Calibration wizard's columns-per-line ruler now measures the printer's
  true printable width instead of always breaking at whatever width was
  already configured, so it could never detect a wider setting on a rerun.
- Calibration wizard skips the paper-width step (instead of silently
  testing it in a fallback image mode) when none of the image patterns
  printed cleanly.
- Calibration wizard no longer offers or tests character-encoding
  candidates the printer's profile can't actually switch to.
- Calibration wizard's character-encoding checkboxes now show each
  candidate's own expected result, so printers that substitute "?" for
  unsupported characters (e.g. CP437) can pass calibration.
- Saving a calibration now posts a Home Assistant notification with the
  printer-database share link, since the link was previously lost as
  soon as the wizard closed.
- Calibration wizard no longer wipes a step's already-entered selections
  (impl checkboxes, width bar, ruler marker, codepage checkboxes) when
  reprinting that step's test page.
- Calibration wizard now aborts cleanly instead of risking a crash if
  the config entry unloads while the wizard is open (e.g. an HA restart,
  or a reload triggered from another browser tab).

## [1.0.0] - 2026-08-02

### Added

- **`feed_before_cut` option on the `cut` service.** ESC/POS cuts always
  feed ~6 lines of paper before cutting; set `feed_before_cut: false` to
  skip that feed and save paper when you've already positioned the cut
  point. Defaults to `true` (previous behavior). The selected cut mode
  (full/partial) is honored either way; the integration emits the
  `GS V` function-B opcode directly when skipping the feed, since
  python-escpos's own `feed=False` path always cuts partial.
- **Six more hardware barcode types on `print_barcode`**: NW7, GS1-128,
  and the four GS1 DataBar variants (Omnidirectional, Truncated, Limited,
  Expanded), for printers whose firmware supports them.
- **Serial printers now default to a 5-minute connectivity check**
  (`status_interval: 300`). Previously the "Online" sensor for serial
  printers only updated when something printed, so an unplugged printer
  could read Online indefinitely; the serial probe is a silent `os.stat`
  of the device node, so the check is free. Network/USB printers are
  unaffected (their paper-status poll already doubles as a health
  check). Bluetooth deliberately stays opt-in (`0`): each BT status
  check opens a real RFCOMM connection, and many cheap printers audibly
  beep on every connect. An explicitly configured `status_interval` is
  respected as before.
- **Reconfigure flow** for all four connection types (**Settings** →
  **Devices & services** → printer → **Reconfigure**). A printer whose IP
  address, serial port, USB device, or Bluetooth MAC changes can now be
  updated in place; previously the only option was delete and re-add,
  which broke every automation targeting the device. Network/serial
  reconfiguration updates the entry identity (the address *is* the
  identity); USB/Bluetooth abort if re-pointed at a different physical
  device.
- **Explicit `broadcast` option** on all printer-targeting services.
  Omitting `device_id` still prints to all configured printers (kept for
  backward compatibility), but now logs a warning when more than one
  printer is configured; set `broadcast: true` to fan out intentionally
  (mutually exclusive with `device_id`).
- **`serial_number` on the device entry for USB printers**, when the
  device reported one during setup, visible in **Settings** → **Devices
  & services** → device page. Network/Bluetooth/serial transports are
  unaffected.
- **Service and field names/descriptions are now translatable.** Every
  service (`print_text_utf8`, `print_image`, `print_barcode`, etc.) and
  their fields (including the collapsed "Image Options"/"Advanced
  Options" section groups) now have entries under strings.json's new
  `services` key, generated from `services.yaml` by
  `scripts/sync_service_translations.py` so the two can never drift.
- **Every service now has an icon** in the automation action picker: 13
  of the 22 were missing one.
- **`print_message`'s High Density and `print_text_image`'s Auto-Resize
  options are now visible in the UI forms** (previously accepted in
  service calls but absent from the form).

### Fixed

- Service descriptions synced from `services.yaml` no longer carry a
  trailing newline in `strings.json`/`translations/en.json` (hassfest
  rejects leading/trailing whitespace in translation strings).
- The serial config/reconfigure flows now initialize the baudrate on
  every code path; previously a rejected baudrate left the variable
  unassigned (flagged by CodeQL, unreachable in practice).
- **`preview_box` / `preview_table` showed "Translation error:
  INVALID_ARGUMENT_TYPE" in the service UI.** Their descriptions contained
  literal `{path, width, line_count, codepage}` text, which the frontend's
  ICU message parser read as a malformed placeholder. Reworded without
  braces; a regression test now rejects any non-`{identifier}` braces in
  user-visible strings.
- **`print_table` / `preview_table` "Rows" tooltip showed a garbled
  example.** The description used a YAML block list, which the frontend
  flattens onto one line (`- ["Item", ...] - ["Coffee", ...]`). The
  examples now use flow syntax (`[["Item", "Qty", "Price"], ...]`) that
  reads correctly inline and can be pasted as-is.
- **Seven exception messages showed literal `{placeholder}` text instead
  of the actual value.** ICU quoting rules treat an apostrophe before `{`
  as an escape, so `'{value}'` rendered as the literal text `{value}` in
  the frontend. Those messages now quote values with `"` instead, and the
  same regression test rejects `'{`/`'<` sequences.
- **Serial printers with an explicitly selected profile failed on every
  print.** The serial adapter passed the resolved profile *object* into
  python-escpos, whose profile lookup only accepts the profile *name*, so
  any real profile (e.g. TM-T20II) raised `KeyError` on connect. Setup
  appeared to succeed. The failure only surfaced when printing. The
  default `profile: auto` was unaffected.
- **Reconfiguring a serial printer silently reset its baudrate to 9600.**
  The stored baudrate (an integer) never matched the reconfigure form's
  string-keyed dropdown, so the current value didn't preselect and an
  untouched submit fell back to the default.
- **`print_barcode` with type `ITF14` failed on every print.** The type
  passed validation but python-escpos has no `ITF14` entry in its barcode
  name maps, so the library raised `BarcodeTypeError`. ITF-14 is a
  14-digit ITF (there is no separate hardware opcode), so it is now
  printed as `ITF`. A test now checks every type offered in the service
  selector resolves to a printable python-escpos type.
- **Reconfiguring a USB printer now preselects the currently configured
  device** in the device dropdown instead of the first discovered one.
  (Submitting the wrong preselection was already rejected; this fixes
  the confusing form state, not a data-loss path.)
- **`print_separator` now clamps its width to the printer's line width**,
  matching `print_box`/`print_table`/`print_kvtable`. Previously a width
  above the configured line width re-wrapped into multiple lines of
  separator characters.
- **"Translation error: UNCLOSED_TAG" shown instead of several field
  descriptions in the service UI** (e.g. the Image field on Print
  Formatted). The frontend parses translation strings as ICU messages, so
  angle-bracket placeholders like `camera.<id>` or `<config>/fonts/` were
  read as unclosed rich-text tags. All such placeholders now use square
  brackets (`camera.[id]`), and a test guards against reintroducing
  tag-like `<` in `services.yaml`, `strings.json`, or `en.json`.
- **The "Battery" sensor's static `mdi:battery` icon has been removed** so
  Home Assistant's built-in dynamic battery-level icon (which reflects the
  actual charge percentage) is used instead. `icons.json` also dropped a
  dead `binary_sensor.status` key left over from a since-renamed entity.
- **Diagnostic-only attributes (connection probe timestamps/latency, last
  image-print stats) no longer get written to the recorder database** on
  every state change; they're excluded via `_unrecorded_attributes`,
  cutting needless history-table churn. The stable `connection_type`
  attribute is still recorded.
- **The "Online" connectivity sensor could latch on and never report
  offline.** Failed print operations now mark the printer offline
  immediately, and `print_barcode`, `feed`, `cut`, and `beep` now mark it
  online on success (previously only text/QR/image prints did). Invalid
  barcode payloads deliberately do *not* affect connectivity state: only
  real transport failures do.
- **The "Online" connectivity sensor stayed "unknown" until the first
  print** on a default install, because status polling is off by default
  (`status_interval: 0`) and no probe ran before then. The adapter now
  always runs a one-shot status probe at startup regardless of
  `status_interval` (the option still only controls the *recurring*
  probe). The paper-status sensor's periodic poll (network/USB only) now
  also feeds the connectivity sensor, so it gets free updates between
  prints instead of only on a failed paper-status query being silently
  discarded.
- **The "printer profile is missing pixel width" repair issue could
  persist forever**, and two printers sharing the same profile name
  could clobber each other's issue. It's now scoped per config entry,
  cleared automatically once the profile resolves (or the printer is
  removed), instead of only ever being created and never deleted.
- **Diagnostics downloads omitted several options** (serial write
  chunk size/delay, `allow_local_image_urls`, default align/cut,
  reliability profile) needed for triage: only a hand-picked subset was
  reported. The full options dict is now included (still redacted).
- Both `should_poll` sensors (Bluetooth battery, paper status) were
  documented as polling every 5 minutes but had no `SCAN_INTERVAL` set,
  so they used Home Assistant's 30-second default: 10x more D-Bus
  round-trips / printer connections than intended.
- **USB printers that don't report a serial number now get a stable
  unique ID** (`usb:VID:PID`), preventing the same printer from being
  added twice. This includes manual VID:PID entry, where custom
  endpoints are folded into the ID so distinct same-model setups still
  coexist.
- **USB reconfigure could dead-end with "Unique ID mismatch"** for
  printers originally added with a serial number (or custom endpoints),
  because the flow recomputed the ID without the suffix the reconfigure
  form couldn't know. Reconfigure now keeps the entry's identity when
  the VID:PID matches; pointing at a genuinely different device still
  aborts. The form also no longer silently resets a tuned timeout back
  to the default on submit.
- **USB manual setup rejected the 0x-prefixed hex VID/PID format its own
  help text recommends**: the fields only accepted bare integers. Hex
  (`0x04B8`), decimal strings, and plain integers all work now.
- **Options-flow validation errors displayed as raw keys** (e.g.
  `invalid_profile`) instead of readable messages; the translations
  existed only under the config-flow namespace. The `already_in_progress`
  abort message was also missing.
- **Opening Options on a Bluetooth printer and pressing Submit silently
  changed print behavior**: the form displayed `bluetooth_safe` as the
  reliability profile while runtime actually used `auto`. The form now
  shows the value runtime uses.
- **Calibration sheets printed at a different width than real images**
  when no printer profile is configured: the image pipeline fell back to
  512 px while `calibration_print`/`print_text_image` used 384. Unified
  on 384 (58 mm-safe at 203 dpi; 512 clipped 58 mm heads). Note for 80 mm
  printers without a profile selected: images now print at ~2/3 paper
  width instead of ~89%: select your printer's profile or set
  `image_width: 576` for full width (see the Images guide, "How the
  target width is chosen").
- **`print_kvtable` with a tiny `total_width` (3–4) raised a raw internal
  error**; it's now a proper validation error naming the minimum for the
  chosen border style.
- **Box/table/kvtable layouts wider than the printer's line width were
  shredded by re-wrapping**; `total_width` is now clamped to the
  configured line width, with a warning naming both numbers. Explicit
  `print_table` `column_widths` that can't fit the printer now raise a
  clear validation error instead of an internal one.
- **`preview_image` rejected `cut`/`feed`**, so a working `print_image`
  call couldn't be pasted into it unchanged; they're now accepted (and
  ignored, like the other printer-communication knobs).
- **Serial connection retries leaked a port handle** each time opening
  the port failed.
- **A python-escpos keyword-signature mismatch could print duplicate
  image/barcode fragments**: unsupported keywords were detected by
  catching the error and re-sending, which duplicated any bytes already
  written. Capability detection now happens up front via signature
  inspection.
- **Device actions offered cut modes the printer's profile doesn't
  support** (e.g. full cut on partial-only cutters); the choices are now
  profile-gated, matching the config flow.
- **`print_barcode`**: an explicit `align` was silently overridden by
  the default center-align (`align_ct`); explicit `align` now wins
  unless `align_ct` is also explicitly set (calls setting neither behave
  exactly as before).
- **`print_text_image`**: the `image_threshold` description wrongly
  claimed it applies when `dither` is `"none"`.
- (internal) Config entries now declare `MINOR_VERSION = 1`; existing v3
  entries left at minor version 0 are normalized on load so future
  minor-version migrations aren't skipped.
- (internal) Device-to-config-entry resolution now prefers
  `DeviceEntry.config_entry_id` when present, falling back to the
  deprecated `config_entries` set, forward-compat with HA 2026.8+ ahead
  of that attribute's 2027.8 removal.
- **A printer connect failure during any print, feed, cut, beep, or
  barcode operation now correctly marks the printer offline and
  notifies the connectivity sensor.** Previously only a failure *after*
  a successful connect flipped the sensor; a failure during the connect
  itself went unreported.
- **`beep()` no longer reports success when the buzzer command fails at
  the transport level.** The error now propagates and the connectivity
  sensor flips offline, instead of the operation silently completing.
- **Image decode failures no longer echo the fetched response's raw
  bytes back to the service caller.** The error message surfaced to the
  caller still reports the declared content type and payload size; only
  the leading-byte sniff used to detect an HTML error page is now
  debug-logged instead of being included in that message.
- **Unchanged printer status no longer redundantly re-fires the
  connectivity sensor on every paper-status poll.**
- **Reconfiguring a legacy USB entry onto a device already owned by
  another entry now aborts with "already configured"** instead of
  creating a duplicate unique ID.
- **USB reconfigure now probes using the entry's stored endpoints**
  instead of the defaults.
- **Reconfiguring a network or serial printer to a new address now
  updates the entry/device title** when it was still auto-generated
  (manual renames are preserved).
- **Removing a config entry now also cleans up its legacy
  profile-name-scoped repair issue.**
- **The barcode `force_software` selector no longer labels the wrong
  option as the default.**

### Security

- **Image source fields (`image`, `fallback_image`) are no longer
  rendered as Jinja templates inside the integration.** Server-side
  rendering ran without Home Assistant's per-user state-read permission
  checks. Templates in automations and scripts are unaffected; Home
  Assistant renders those before the service is called. Only raw
  `{{ ... }}` strings typed directly into Developer Tools → Actions are
  now treated as literal text instead of being evaluated.
- **The Print Image device action bypassed per-user camera/image entity
  permission checks**: it invoked the printer without the calling user's
  context, so a non-admin could print camera frames a direct service call
  would refuse with `Unauthorized`. The action now passes the context
  through, enforcing the same entity ACL on both paths.
- **`print_image_path` / `print_image_url` schema guards now strip
  whitespace before checking the source shape**, closing a gap where a
  leading/trailing-whitespace value could dodge the per-service
  URL-only / local-path-only validator.
- **Local image and font path validation now checks the allowlist
  before any existence/extension/size check**, closing a
  filesystem-enumeration oracle where a disallowed path's error message
  differed depending on whether the file existed.
- **Blocked the Alibaba Cloud metadata endpoint (`100.100.100.200`).**
  CGNAT-space addresses (`100.64.0.0/10`) were previously treated as
  publicly routable and reachable even without the "Allow local image
  URLs" opt-in; this specific cloud-metadata address inside that range
  is now blocked unconditionally, same as the AWS/link-local metadata
  endpoints.

### Changed

- Documentation punctuation pass: replaced em-dashes across the README,
  docs/, blueprints/, and repo-root markdown with conventional punctuation.
- **The "Last image print" diagnostic sensor and the Bluetooth "Battery"
  sensor are now disabled by default.** Both are niche diagnostics (the
  battery sensor only reports on the rare printers exposing BlueZ
  `Battery1`); enable them from the entity registry if wanted. Existing
  registry entries keep their current enabled state.
- **`print_text_image` no longer accepts `image_rotation` /
  `image_align`**: both were silently discarded (the service's own
  alignment and orientation apply), so passing them is now a validation
  error instead of a no-op.
- Service-call validation failures (bad URLs/paths, invalid barcode or QR
  data, oversized images, disallowed font paths, malformed options, etc.)
  are now raised as `ServiceValidationError` with translation metadata
  instead of a generic `HomeAssistantError`. Home Assistant now surfaces
  these as user input errors (rather than integration faults) and they are
  translatable; genuine printer/transport failures are unaffected.
- Service forms group optional fields into collapsed "Image Options" /
  "Advanced Options" sections (`print_image` family, `preview_image`,
  `print_message`, `print_text_image`, `print_barcode`); UI-only, call
  data is unchanged and existing automations are unaffected. Removed the
  redundant `center` / `image_center` / `align_ct` toggles from the UI
  forms; they're still accepted in service calls (use `align: center`
  instead). Advanced transport knobs no longer require HA "advanced
  mode" (now in the collapsed Advanced Options section).
- Now available in the HACS default store; installation docs updated to
  drop the custom-repository steps.
- Dropped `Pillow` and `dbus-fast` from `manifest.json` requirements: both
  are provided by Home Assistant core, and pinning them from a custom
  integration can conflict with core's own constraints on upgrade (HACS
  default-store review feedback). Pillow is still installed transitively
  via `python-escpos`; Bluetooth discovery already degrades gracefully if
  `dbus-fast` is unavailable.
- **The documented 60-second Bluetooth status-interval floor is now
  enforced in the options flow.** `0` still disables polling; `1`–`59`
  is now rejected instead of silently accepted.
- **The connectivity binary sensor now uses Home Assistant's dynamic
  connectivity icons** instead of a static printer icon, so its icon
  reflects the actual connected/disconnected state.
- **Docs:** corrected the status-interval default (`0`/disabled, not
  30 s), fixed a broken CJK section anchor, and documented the
  last-image-print diagnostic sensor.

## [0.8.0] - 2026-07-20

### Breaking changes

- **Minimum Home Assistant version raised to 2026.5.0.** The serial
  connection type requires `SerialPortSelector`, which was introduced in
  HA 2026.5.0 and is absent in 2026.3/2026.4. Because the selector is
  imported at module level via the config flow, loading the integration
  on an older HA version breaks the config flow for *all* connection
  types, not just serial.

### Added

- **Paper status sensor** (#109). Network and USB printers get a
  `Paper status` enum sensor (`ok` / `low` / `out`) backed by the
  ESC/POS real-time DLE EOT paper-sensor query, so automations can
  notify when paper runs low or out. Bluetooth and serial printers
  don't get the sensor: those transports are write-only in this
  integration, and python-escpos reports an empty read as "plenty of
  paper", a false OK. The last polled value also appears in the
  diagnostics download as `paper_status`.

- **Serial (UART/RS-232) printer support.** Printers connected via a
  physical serial cable (`/dev/ttyUSB0`, `COM3`) or a network-based
  serial proxy can now be configured as a new connection type. Supported
  URL schemes: `esphome://host:6053?port_name=Name` (ESPHome
  `serial_proxy` component), `rfc2217://host:port` (RFC 2217 serial
  servers), and `socket://host:port` (raw TCP). Requires HA ≥ 2026.5.0
  (introduces `SerialPortSelector`) and serialx ≥ 1.7.0 (pinned by HA
  core's `package_constraints.txt`).
- **Write chunking for ESP32/serial buffer overruns.** Two new options
  under **Configure**: *Write chunk size* (bytes per write call,
  0 = disabled) and *Inter-chunk delay* (ms between chunks), allow
  the integration to pace output to devices with small UART FIFOs (e.g.
  ESP32 via ESPHome `serial_proxy`). Recommended values: chunk size 128,
  delay 10 ms. Both are validated in the options flow (0–4096 bytes,
  0–1000 ms) to prevent runaway `time.sleep()` calls under the print
  lock. Because serial writes are coalesced and only sent to the wire at
  flush time, the payload is now flushed with error propagation before the
  connection closes: a failed write (unplugged adapter, dropped proxy)
  surfaces as a failed print instead of silently reporting success.
- **Serial printer status sensor.** The binary sensor checks device-path
  ports via `os.stat` + `S_ISCHR` (non-invasive, no open required) and
  URL-based ports via a brief open/close probe, consistent with the
  Bluetooth reachability model. The probe runs under the operation lock,
  so it never opens a second connection to a URL proxy while a print is in
  flight.
- **Serial port redaction in diagnostics.** The serial port path or URL
  is included in the diagnostics download but redacted by
  `async_redact_data` (same treatment as network host and Bluetooth MAC).

### Changed

- **Dependency bump: `wcwidth` 0.8.1 → 0.8.2.** Upstream bugfix for an
  `IndexError` when a measured index exceeds the string length. No
  configuration or service changes.
- **Dev/CI stack moved to the HA 2026.6.3 test harness**
  (`pytest-homeassistant-custom-component` 0.13.333 → 0.13.339). Dev
  pins follow HA 2026.6.3's `package_constraints.txt`: `serialx`
  1.7.3 → 1.8.0 and `dbus-fast` 4.0.4 → 5.0.16 (both already inside
  the `manifest.json` ranges, so end-user installs are unchanged), plus
  `ruff` 0.15.18 → 0.15.22. The pip-audit ignore list in
  `security.yml` was rebuilt against the new stack (clears the stale
  Pillow/aiohttp/PyJWT/requests/pytest/uv entries; adds the current
  HA-pinned Pillow 12.2.0 / aiohttp 3.13.5 / cryptography 48.0.0 /
  PyJWT 2.12.1 advisories, all fixed only in versions no HA release
  ships yet). **The minimum supported HA version for users is
  unchanged at 2026.5.0.**
- **README requirements corrected** to state the actual minimum of
  Home Assistant 2026.5 (previously still said 2026.3; the floor was
  raised when serial support landed).
- **Dependency bump: `wcwidth` 0.7.0 → 0.8.1.** Picks up upstream's
  terminal-aware width fixes (notably Variation Selector 15 emoji now
  measured as narrow), which feeds the visual-column padding for the
  text-effects box / table layouts. No configuration or service changes.

## [0.7.4] - 2026-06-12

### Fixed

- **0.7.3 broke every print on entries with a configured printer
  profile** (`Service … failed: <escpos.capabilities.TMT20IIProfile
  object at 0x…>`). The 0.7.3 profile fix passed the *resolved profile
  object* into the python-escpos printer constructors, but
  `Escpos.__init__` re-runs that kwarg through `get_profile()`, which
  only accepts a profile *name*; the object fell through to a dict
  lookup keyed by the object itself and every connect raised `KeyError`.
  The adapters now hand over the validated profile name; an unknown
  profile still degrades to the library default with a debug log. The
  test-suite escpos fakes now mirror the real constructor's profile
  round-trip so this class of bug can't slip through again.
- **URL image fetches identify as Home Assistant again.** The
  SSRF-hardened per-request fetch session sent aiohttp's default
  `Python/3.x aiohttp/…` User-Agent, which CDN/WAF bot rules
  (WordPress/Photon, Cloudflare) often answer with an HTML block page
  served as 200, surfacing as `cannot identify image file`. The session
  now sends HA's own User-Agent (as the pooled clients did pre-0.7) plus
  an Accept header biased toward the decodable image formats.
- **Undecodable image bytes now produce an actionable error.** Instead
  of Pillow's bare `cannot identify image file <_io.BytesIO …>`, the
  error reports the declared content type, payload size, and the leading
  bytes, and calls out the likely HTML-error/bot-block page when the
  body looks like HTML.

## [0.7.3] - 2026-06-12

### Fixed

- **Configured printer profile was never applied, and image width fell
  back to 512 px on nearly every install.** `_get_profile_obj()`
  imported `get_profile` from the removed `escpos.profile` module
  (python-escpos 3.x moved it to `escpos.capabilities`); the
  `ImportError` was swallowed, so the profile was silently dropped at
  connect time. Separately, `get_profile_pixel_width()` read the width
  from the live connection, which is `None` for USB, Bluetooth, and
  non-keepalive network printers, so the width lookup always missed and
  filed a spurious Repairs issue. Width is now read from the configured
  profile object, and the fallback warning/Repairs issue only fires when
  you actually selected a profile that lacks a pixel width (the
  auto/default profile falls back silently, as intended).
- **Options changes (codepage, profile, line width, keepalive,
  reliability profile, "Allow local image URLs", …) now take effect
  immediately** instead of requiring an HA restart. The entry reloads on
  an options update.
- **Codepage / profile can be reset back to "(Default - Auto)" in
  options.** The previous `options or data` fallback treated the empty
  "auto" value as falsy and snapped the original setup value back.
- **`fallback_image` now actually works** on all image services and the
  notify `print_message`. The schema produced a `Template` object that
  the resolver rejected, so the fallback could never fire.
- **A keepalive connection is dropped after a failed operation** instead
  of being reused. A single transient error (power-cycle, idle timeout)
  no longer bricks all subsequent prints until the entry is reloaded.
- **`print_text`'s `encoding` override no longer prints mojibake.** It
  called the removed `_set_codepage`; it now selects the codepage via
  `charcode`.
- **Setup now retries with backoff** (`ConfigEntryNotReady`) when the
  printer is unreachable at startup, instead of hard-failing the entry.
- **Multi-printer service calls attempt every target** even if one
  fails, and report an aggregate error naming the failed printer(s) and
  how many succeeded. Targeted devices that aren't loaded are logged
  instead of silently skipped.
- **`print_barcode`'s `align` option is honoured** (it was accepted and
  advertised but ignored).
- **Focused image services feed the advertised number of lines** for
  script/automation callers (the schema now injects the per-service
  `feed` default, matching the UI).
- **The `beep` service UI now advertises its real defaults** (2 beeps,
  duration 4) instead of 1/1.
- **Config flow: selecting both "Custom codepage" and "Custom line
  width" at setup no longer drops the custom width.**
- **Diagnostics correctly label Bluetooth entries** (was reported as
  `network` with null host) and redact the BT MAC, host, and the entry
  title (which embeds the host:port or MAC).
- **Network config flow normalises the unique ID** (case-insensitive
  host) so the same printer isn't added twice, and validates the port
  range.
- **USB auto-discovery now covers the generic POS-printer VID `0x0FE6`**,
  syncing `manifest.json` with the known-VID list in `const.py` (a sync
  test now guards against future drift).

### Security

- **Barcode data with embedded control bytes is rejected.**
  `print_barcode` did not strip ESC/GS/NUL/C0 bytes (unlike text input)
  and defaulted `check=False`, so a crafted payload could terminate the
  barcode early and inject raw ESC/POS commands (e.g. a cash-drawer
  kick).
- **The "Allow local image URLs" opt-in no longer lifts the port
  allowlist for public targets.** Non-standard ports are now permitted
  only for resolved private/LAN addresses, closing a blind port-scan
  oracle against arbitrary internet hosts.
- **Notify `print_message` enforces the calling user's entity
  permissions** for `camera.*` / `image.*` sources. The service context
  was lost on the entity-service path, so the per-entity read ACL was
  bypassed. The context is captured before any `await` so concurrent
  calls can't race it.
- **Multi-printer calls fail closed on authorization/validation errors.**
  An `Unauthorized` or `ServiceValidationError` on any target propagates
  immediately with its context instead of being aggregated into a
  generic "N of M failed" message.

### Changed

- **Pillow's process-global decompression-bomb limit is no longer
  lowered.** The 20 M-pixel cap is enforced per-decode against the image
  header instead, so other Home Assistant integrations sharing the
  process keep Pillow's default limit on legitimate large photos. With
  `auto_resize` the per-decode ceiling rises to 40 M pixels (the image is
  downscaled after decode), preserving the large-source workflow.
- **`iot_class` corrected to `local_polling`** (reachability is polled).
- Status reachability probes now hold the operation lock atomically
  (closing a check-then-probe race with in-flight prints), and the
  adapter is torn down on the executor thread under the lock.
- **The integration is no longer geo-restricted in HACS** (`country`
  removed from `hacs.json`).
- Service descriptions in Developer Tools now come from `services.yaml`
  for every service; a stale partial translation block that overrode
  nine of them with worse text was removed. Added the missing Repairs
  and `reliability_profile` option translations. Made the network
  `cannot_connect` error actionable.
- **The RFCOMM channel field on the Bluetooth setup form moved into a
  collapsed "Advanced options" section.** It was previously shown only
  when "Advanced mode" was enabled on your HA user profile; that flag is
  deprecated (removal in HA 2027.6) and newer HA versions hard-wire it
  on, which would have surfaced the field for everyone. The section is
  always available (expand it to set a non-default channel) and a
  refused default channel still routes to the focused channel-retry
  step.

## [0.7.2] - 2026-06-11

### Added

- **"Allow local image URLs" printer option** (issue #95). Image URL
  fetches (`print_image_url` and the other image services) still reject
  private/LAN/loopback targets and non-standard ports by default (an
  SSRF guard), but you can now opt in per-printer (**Configure → "Allow
  local image URLs"**) to print from a LAN camera, an NVR/Frigate proxy
  (e.g. `:5000`), a NAS, or your own Home Assistant instance (`:8123`).
  Enabling it lifts both the private-address block and the default-port
  (80/443) restriction. The dangerous ranges stay blocked even when
  enabled: link-local/cloud-metadata (`169.254.0.0/16`, `fe80::/10`, and
  the AWS IMDSv6 endpoint `fd00:ec2::254`), multicast, reserved
  (`240.0.0.0/4`), and unspecified. The fetch sends no auth token, so
  only unauthenticated endpoints work, and `print_image_url` has no
  per-user authorization: enabling the option lets any HA user or
  automation reach LAN hosts/ports through that printer. The strict-mode
  rejection messages now point at the new toggle. See
  [docs/images.md](docs/images.md#allowing-local--lan-urls).

### Fixed

- **HTTP/HTTPS image-URL printing failed for every URL** with
  `Cannot connect to host <host>:443 ssl:default [None]` (issue #95).
  The DNS-pinning `_StaticResolver` only answered lookups for an
  explicit `AF_INET` / `AF_INET6` family, but `aiohttp.TCPConnector`
  resolves with `AF_UNSPEC` (0) by default, so every fetch matched no
  address bucket and raised a `strerror`-less `OSError` that surfaced as
  the misleading `[None]` connect error. `AF_UNSPEC` now returns all
  pre-validated addresses, each tagged with its real family. The
  DNS-rebinding defense is unchanged (still pinned to the one validated
  hostname and its pre-resolved IPs). `print_image_url` and the other
  URL-backed image services now work again. Added an `AF_UNSPEC`
  regression test plus a guard locking in aiohttp's default family.

## [0.7.1] - 2026-05-26

### Breaking changes

- **`blueprints/automation/escpos_printer/todo_item.yaml`** input
  renamed from `box_style` → `style` to match the convention used by
  every other blueprint in the pack (the 5 new ones, plus the 8
  pre-existing). Existing scripts created from this blueprint will need
  to be re-saved (HA will show the input as unset on the next edit and
  default it to `auto`). The single-input change is otherwise
  semantically identical: same border-style options, same default.

### Added

- **`blueprints/automation/escpos_printer/doorbell_snapshot.yaml`**:
  on doorbell button / motion / state-trigger entity firing, prints a
  titled camera snapshot (via `print_camera_snapshot`) with a "From /
  Time" footer. Configurable rotation, dither mode, and border style.
  The snapshot service call carries `continue_on_error: true` so a
  camera that's offline or mid-reboot still produces the title +
  timestamp slip rather than silently skipping the whole automation.
- **`blueprints/automation/escpos_printer/morning_briefing.yaml`**:
  single morning slip combining a date header, optional weather
  forecast table, optional today's calendar agenda, and a templated
  one-line footer. Each section is independently optional: leave the
  matching entity blank to skip. Defensive against null `temperature` /
  `condition` from providers (accuweather, met.no fallback) and against
  all-day calendar events (which return `start` as `{date: "..."}`
  rather than a string, caught both crashes during pre-merge review).
- **`blueprints/automation/escpos_printer/trash_reminder.yaml`**:
  fires daily at a configured time and looks at the target weekday
  (`offset_days` default 1 = tomorrow's bins; set to 0 with an earlier
  `print_time` for a morning-of reminder). Seven per-weekday text
  inputs hold bin descriptions; empty days silently skip so the
  reminder only prints on the actual pickup days.
- **`blueprints/automation/escpos_printer/todo_ticket.yaml`**:
  upgraded counterpart to `todo_item`. Per new task, prints a
  job-ticket slip with a bold double-width title (pure text mode:
  works on image-less printers), a Due / List / Added KV table,
  optional description, and a QR code linking back to the source task.
  `url_template` is a Jinja template with `uid` / `summary` / `due` /
  `description` in scope (default targets Todoist's web URL); QR
  auto-skips when `uid` is empty so the blueprint is safe across mixed
  back-ends (local lists, Google Tasks). Header text ("NEW TASK") is
  configurable via the `header_text` input. New-item detection diffs
  on `uid` first (with summary fallback) so two tasks with the same
  title don't dedup and renames don't look like add+drop.
- **`blueprints/script/escpos_printer/guest_wifi_qr.yaml`**: prints
  a scannable Wi-Fi QR encoding the standard
  `WIFI:T:<auth>;S:<ssid>;P:<pass>;H:<hidden>;;` URI (supported by iOS
  / Android / most laptop camera apps), with proper backslash-escaping
  of reserved characters in SSID and password, plus optional plaintext
  fallback for devices without a QR scanner.
- **`blueprints/UNIFI_GUEST_WIFI.md`**: opinionated, ~10-minute
  recipe pairing the Guest Wi-Fi QR blueprint with the **official HA
  UniFi integration**. One shell script (`unifi_wifi.sh` with `read` /
  `rotate` actions) that pulls credentials directly from HA's existing
  UniFi config entry (`.storage/core.config_entries`) via `jq`: no
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
- **`blueprints/README.md`**: table rows, import badges, and
  per-blueprint notes for the five new entries (including
  back-end-specific URL patterns for the TODO Ticket blueprint, an
  emoji-rendering caveat for text-mode summaries, and a TODO Item /
  TODO Ticket decision rule). Slimmed from 336 → 147 lines after
  splitting two long sections into their own files (see below); now
  acts as the catalogue index with brief per-blueprint notes and
  pointers to the deeper guides.
- **`blueprints/AUTHORING.md`** (new): the full blueprint-authoring
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
- **`blueprints/GUEST_WIFI_QR.md`** (new): Guest Wi-Fi QR setup
  guide split out of the README's per-blueprint notes (which had
  grown to ~65 lines of effectively-a-tutorial under what should be
  a 3-line note). Covers the 2-minute Quick start, helper-backed
  credentials, automated rotation pointer, and ZXing WIFI URI
  format details. `UNIFI_GUEST_WIFI.md`'s "Don't need automation?"
  callout now points here rather than at the README. The Guest Wi-Fi QR section now leads
  with a "Quick start (works on any router, about 2 minutes)" 6-step
  walk-through that gets a non-technical user from blueprint import
  to a printed scan-ready slip without touching YAML or shell
  scripts. Beneath it: a "store credentials in helpers" step for
  users who want to edit creds without editing the script, and an
  "Automating rotation" section that covers UniFi (link to deep
  doc), other API-capable routers, and the manual-rotate-with-
  reminder fallback for ISP modems / consumer APs with no API.
  Format / ZXing details moved to the bottom so they don't
  intimidate first-time users. Includes a security note about the
  TODO Ticket `url_template` input: it's rendered with HA's full
  template scope, so a malicious fork could exfiltrate secrets via
  the QR payload (humans don't read QRs; their phones do).

### Fixed

- **`blueprints/automation/escpos_printer/trash_reminder.yaml`**:
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
  `receipt.yaml`**: both bundled scripts swapped their large serif
  header from `print_text_image` (raster) to `print_text_utf8`
  (double-width / double-height / bold, text-mode). The
  image-rendered headers looked nicer but failed silently on the
  many ESC/POS printers that don't implement the raster image
  command family (notably several Bluetooth POS-58 units and
  budget USB models). Text-mode headers print on every supported
  printer and still transcode UTF-8 (accents, smart quotes) via the
  codepage. Users who specifically want the typographic header can
  re-add `print_text_image` in a fork: it's a one-line change in
  each blueprint.
- **`blueprints/script/escpos_printer/recipe_card.yaml` and
  `blueprints/automation/escpos_printer/todo_ticket.yaml`**: text
  sanitiser chain now strips `\r` (left over from Windows `\r\n` line
  endings after splitting on `\n`) in ingredient/step rows and in
  task descriptions. Previously, pasted-from-Windows content rendered
  with stray carriage returns. `\n` is still preserved inside
  multi-paragraph task descriptions (`print_text_utf8` wraps them
  correctly).

### Added (CI / tooling)

- **`scripts/extract_markdown_bash.py`**: extracts fenced ```bash```
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
  `.pymarkdown.json`): disables MD013 (line length, incompatible with
  prose-style markdown), MD036 (bold-as-pseudo-heading is intentional
  for `**Inputs:**` / `**Notes:**` in-paragraph labels), narrows MD024
  to siblings-only (so the CHANGELOG's repeated `### Added` headings
  under different `## [version]` parents are allowed), and disables
  MD041 (first-line top-level-heading false positive for
  callout-prefixed docs). Hook scope: **every `.md` file** the repo
  tracks (excluding `dist/`, `.full-review/`, build / cache dirs).
  All 31 existing markdown files now lint clean.
- **`scripts/md_fix.py`**: safe targeted fixer for MD022 / MD031 /
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
- **`.pre-commit-config.yaml`**: the `validate-blueprints` hook's
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
  clobber it with rendered PNG bytes, CWE-862/CWE-552), user-supplied
  `output_path` values outside the system temp directory are rejected
  with `HomeAssistantError`. If your automation needs the file in
  `/config/www/`, add a second step that copies the returned `path`.

### Added

- **Text-effects services**: seven new services for receipt-style
  layouts that work within the 1-col-per-glyph thermal text mode:
  - `escpos_printer.print_box`: wraps text in a printable border.
    `style: auto` picks Unicode single-line `┌─┐` on CP437-capable
    profiles and falls back to ASCII (`+-+`) elsewhere; explicit
    `single` / `double` / `ascii` / `asterisk` / `hash` are honored
    when the user wants a specific look.
  - `escpos_printer.print_table`: multi-column rows with per-column
    `column_aligns` (`left` / `center` / `right`), optional header
    separator, and the same border-style picker as `print_box`.
  - `escpos_printer.print_kvtable`: two-column label/value pairs
    (subtotals, sensor readings, receipt totals) with auto-aligned
    values on the right edge of the printable width.
  - `escpos_printer.print_separator`: a single decorative rule
    (line of repeated characters) at the current printable width.
  - `escpos_printer.print_text_image`: renders text via a TTF/OTF
    font (DejaVu trio bundled, custom fonts dropped into
    `<config>/fonts/` or anywhere in `allowlist_external_dirs`),
    rasterises to a 1-bit image, and prints. Supports 90/180/270°
    rotation, font size, alignment, threshold dither, useful for
    glyphs the printer's codepage doesn't carry (CJK, emoji,
    decorative scripts).
  - `escpos_printer.preview_box` / `escpos_printer.preview_table`:
    render the same layouts to a `.txt` file in the system tempdir
    (default `/tmp/escpos_preview_<entry>.txt`) without printing, so
    users can tune column widths and border styles without burning
    paper. Returns `{path, width, line_count, codepage}` so a
    follow-up step can copy the file or chain a notification.
- **Bundled DejaVu fonts**: `DejaVuSans.ttf`, `DejaVuSansMono.ttf`,
  `DejaVuSerif.ttf` (release 2.37) ship with the integration for
  `print_text_image` to work out of the box. Bitstream Vera license
  text included at `custom_components/escpos_printer/fonts/LICENSE`
  and `NOTICE` at the repo root.
- **Auto-created `<config>/fonts/` directory** on integration setup.
  Any TTF/OTF dropped in is trusted by `print_text_image.font_path`
  without needing an `allowlist_external_dirs` entry: removes the
  "I dropped a font in /config/fonts/ and got an allowlist error"
  friction. Files anywhere else still go through the standard
  allowlist check.
- **Bundled HA blueprints** in `blueprints/`, eight ready-to-import
  scripts and automations exercising the text-effects services:
  - Scripts: `shopping_list`, `todo_list`, `weather_forecast`,
    `receipt`, `recipe_card`.
  - Automations: `daily_agenda`, `sensor_alert`, `todo_item`.
  - `blueprints/README.md` documents import instructions, per-input
    semantics, and troubleshooting.
- **`scripts/validate_blueprints.py`**: YAML structural validator
  that tolerates HA's custom `!input` tag, enforces that each
  blueprint sits under a directory matching its
  `blueprint.domain` (`script` or `automation`), and is wired into
  pre-commit via the new `validate-blueprints` hook plus a CI test
  in `tests/test_blueprints_yaml.py`.
- **`wcwidth==0.2.13`** runtime dependency: `text_effects.width`
  uses it for visual-column measurement so CJK / fullwidth / emoji
  columns line up correctly under the printer's 1-col-per-glyph text
  mode (a naive `len()` silently misaligns).
- **`security.validate_font_path()`**: validates `print_text_image`
  font paths for extension (`.ttf` / `.otf`), file size, symlink
  resolution, and regular-file status, independent of where the path
  lives.
- **`security.validate_rows()`**: typed validator for `print_table`
  rows that enforces consistent column counts, coerces cells to
  strings, and bounds total cell count to protect against
  paper-waste DoS.
- **`security.open_local_font_no_follow()` / `open_local_image_no_follow()`**:
  shared `O_NOFOLLOW`-based reader used by font and image
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
- **Status-vs-print serialisation hardened**: network / USB /
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
  `print_image_entity`, `print_image_url`, and `print_image_path`:
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
- **`auto_resize` option**: accepts source images up to 40 MB and
  downscales them before processing. Removes the friction of "image
  too large" errors on iPhone HEIC / high-res camera snapshots.
- **`fallback_image` option**: if the primary source fails to
  resolve (camera unavailable, URL down, file missing), the integration
  retries the fallback once. Camera/HTTP sources also get a single
  automatic retry with a 500 ms back-off.
- **HEIC / HEIF / AVIF support** when `pillow-heif` is installed (soft
  dependency, no impact on existing setups). iOS-fed camera proxies
  emit HEIC natively.
- **Notify entity accepts unprefixed image keys**: `dither`, `threshold`,
  `rotation`, `invert`, etc. work on `notify.<printer>` without the
  `image_` prefix. Prefixed names still work; prefixed wins on collision.
- **Repair issue** when the printer profile doesn't expose
  `media.width.pixels`. Surfaces the silent 512-px fallback in the HA
  UI with actionable guidance instead of a buried log line.
- **Last image-print diagnostic sensor**: exposes `total_prints`,
  `total_failures`, decoded dimensions, slice count, last error class
  as a polled diagnostic sensor on each printer device.
- **Plain-English `impl` dropdown labels** in the UI: "Raster
  (default: Epson)" / "Graphics (newer ESC/POS)" / "Column (legacy
  POS-58/80)" instead of the raw python-escpos identifiers.
- **Image sources for `print_image` and notify entities.** `image:` now
  accepts URLs (`http://`, `https://`), local file paths, Home Assistant
  camera entities (`camera.<id>`), image entities (`image.<id>`), base64
  data URIs, and Jinja templates that render to any of the above. See
  `docs/images.md`.
- **New `print_image` options**: `image_width`, `rotation`, `dither`
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
  total prints / failures, last error class; never URLs or paths).
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
- **Default `chunk_delay_ms` is now strictly transport-bound**: the
  schema no longer carries a 50 ms default that penalized Network/USB
  callers. Network/USB defaults to 0 ms, Bluetooth to 50 ms, and the
  per-printer Reliability profile can override either.
- **`impl` and `fragment_height` no longer have schema-level defaults**:
  they fall through to the per-printer Reliability profile (Auto
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
  before dithering: transparent pixels now render as white on the
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
  (previously triggered on every httpx exception including HTTP 4xx,
  which silently bypassed HA's middleware) and now uses HA's pooled
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
- Eager slice materialisation in `print_image` removed: slices are
  cropped just-in-time inside the send loop, roughly halving peak
  resident memory on tall images.
- Pipeline now enforces a `MAX_PROCESSED_HEIGHT = 8192` cap and a
  `MAX_SLICES = 64` cap per print: protects against paper-waste DoS.
- `print_image` cancellation now applies a best-effort cut+feed in a
  `finally` block, so cancelling mid-loop no longer leaves the paper
  mid-image.

### Performance

- Image processing pipeline reordered (convert to grayscale before
  rotate/resize). LANCZOS now runs on 1 byte/pixel instead of 3-4
  bytes/pixel: ~3-4× speedup, ~3× peak-memory reduction on RGBA inputs.
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
- **`security.yml` SARIF upload fixed**: emits `bandit -f sarif` instead
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
  `scripts/framework_smoke_test.py`, `scripts/test_network_printer.py`:
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
  style editor when you edit the automation. That's expected; the value
  itself is unchanged.
- For a friendlier UI, switch to the focused service that matches your
  source type: `print_image_url`, `print_image_path` (new),
  `print_camera_snapshot`, or `print_image_entity`. All accept the same
  image-processing options. Migration is optional: `print_image` stays
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
  emulator, no real radio required).
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

Earlier releases: see git history.

[Unreleased]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.8.0...v1.0.0
[0.8.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.7.4...v0.8.0
[0.7.4]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.7.3...v0.7.4
[0.7.3]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.7.2...v0.7.3
[0.7.2]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.7.1...v0.7.2
[0.7.1]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.7.0...v0.7.1
[0.7.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.6.0...v0.7.0
[0.6.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.2...v0.6.0
[0.5.2]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.1...v0.5.2
[0.5.1]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.5.0...v0.5.1
[0.5.0]: https://github.com/cognitivegears/ha-escpos-thermal-printer/compare/v0.4.4...v0.5.0
[0.4.4]: https://github.com/cognitivegears/ha-escpos-thermal-printer/releases/tag/v0.4.4
