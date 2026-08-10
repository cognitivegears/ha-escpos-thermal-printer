# Configuration Reference

Settings that apply to all connection types. For connection-specific options, see [network.md](network.md), [usb.md](usb.md), or [bluetooth.md](bluetooth.md). Don't want to set these by hand? The [calibration wizard](calibration.md) measures several of them for you by printing guided test pages.

After initial setup, click **Configure** on the integration entry to change these.

## Printer Profile

Selects your printer model from the bundled [escpos-printer-db](https://github.com/receipt-print-hq/escpos-printer-db) (~35 profiles). The profile determines available codepages, line width options, supported cut modes, and other capabilities.

- **Generic (no profile)**: works with most printers; use if your model isn't listed.
- **Custom**: type a profile name from escpos-printer-db manually.

### Rebadged and compatible printers

Many cheap thermal printers are rebadges of, or share a command set with,
an already-bundled profile. 23 such clone/equivalent models appear
directly in the profile dropdown as **"Model (compatible)"** entries — for
example, **Epson TM-T20III (compatible)**, **Xprinter XP-80C
(compatible)**, and **Citizen CT-S601II (compatible)** all route to an
existing bundled profile instead of falling back to the generic default.
Typing a model name into the **Custom** profile field also resolves known
aliases, so a bare model number works there too.

If your printer isn't listed at all, use "Generic (no profile)" and,
optionally, run the [calibration wizard](calibration.md) to measure
accurate settings for it directly — no profile required.

## Timeout

Connection timeout in seconds (default 4.0). Increase for slow networks, sleeping printers, or intermittent links. Typical 2–10s.

## Codepage

Character encoding for text. Common options:

| Codepage | Use case |
|----------|----------|
| CP437 | US English, box drawing |
| CP850 | Western European |
| CP852 | Central European |
| CP858 | Western European with € |
| CP1252 | Windows Western European |
| ISO-8859-1 | Latin-1 |
| ISO-8859-15 | Latin-9 (€) |

The dropdown only shows codepages your selected profile advertises. If special characters print wrong, try a different codepage or use the `print_text_utf8` service.

## Line Width

Characters per line:

| Width | Printer type |
|-------|--------------|
| 32 | 58mm paper, small font |
| 42 | 80mm paper, small font |
| 48 | 80mm paper, normal font |
| 64 | 80mm paper, condensed |

## Paper Width in Pixels

Optional override for the target width images are scaled to. Leave empty
to use the selected printer profile's declared width; set it when your
printer has no profile (or the profile doesn't declare a pixel width) and
images print narrower than expected — common values are 384 (58 mm) and
576 (80 mm). The [calibration wizard](calibration.md) can measure this
for you by printing a set of width-test bars. See [How the target width
is chosen](images.md#how-the-target-width-is-chosen) for the full
resolution order.

## Image Printing Implementation

Which ESC/POS image command the integration sends: **Auto** (recommended;
follows the printer profile), **Raster**, **Column**, or **Graphics**.
Override this if images print garbled, stretched, or as stray text under
the Auto setting. The [calibration wizard](calibration.md) test-prints all
three and lets you pick the one that actually rendered cleanly on your
printer. See [Reliability profile](images.md#reliability-profile) for how
this fits into the full implementation-resolution order.

## Default Alignment

Applied when a service call doesn't specify `align`: `left` (default), `center`, `right`.

## Default Cut Mode

Applied when a service call doesn't specify `cut`: `none` (default), `partial`, `full`.

## Keep Alive (network only)

Maintains a persistent TCP connection. Reduces print latency at the cost of misbehaving when the printer goes offline. **Network only.** USB and Bluetooth always reconnect per operation.

## Status Interval

How often to probe the printer (seconds). Default is `0` (disabled) for network, USB, and Bluetooth; **serial defaults to `300`**. A one-shot status probe still runs at startup regardless of this setting, so the binary sensor doesn't stay unknown even with periodic polling off.

- **Network**: any value works; `0` is fine for most setups since print success/failure already updates the sensor.
- **USB**: same as network; `0` is fine, since the status sensor is backed by USB device enumeration rather than a live connection.
- **Serial**: defaults to `300` seconds. Serial has no implicit health check from a paper-status poll the way network/USB do, so without periodic polling an unplugged printer would stay "Online" forever. The probe is a silent `os.stat` on the device path, so polling by default costs nothing.
- **Bluetooth**: defaults to `0` (disabled), deliberately *not* the serial default, even though Bluetooth also lacks an implicit health check. A status check opens a real RFCOMM connection, and many cheap BT printers audibly beep on every connect; default-on polling would beep every 5 minutes. `60` or higher is accepted, and `1`–`59` is rejected with a form error. The integration auto-skips probes during prints, so aggressive polling has no benefit.

## Allow Local Image URLs

Off by default. When enabled, `print_image_url` (and the other image services) may fetch URLs that resolve to private/LAN/loopback addresses **and** use non-standard ports, e.g. a LAN camera, a Frigate proxy on `:5000`, or your Home Assistant instance on `:8123`. By default only public addresses and ports 80/443 are allowed.

Cloud-metadata (`169.254.169.254` and AWS IMDSv6 `fd00:ec2::254`), link-local, multicast, reserved, and unspecified addresses stay blocked even when this is on. The fetch carries no auth token, so only unauthenticated endpoints work.

The option is **per-printer** and is evaluated against the printer you print to. Because `print_image_url` has no per-user authorization, enabling it lets any HA user/automation reach LAN hosts/ports through that printer (an SSRF / port-scan oracle); only enable it where callers are trusted, and prefer camera/image entity sources where possible. See the [Images guide](images.md#allowing-local--lan-urls).

## Reconfiguring a printer's connection

If a printer's connection details change (a new IP address or port, a moved serial device path, a different USB port, or a re-paired Bluetooth adapter), update the existing entry instead of deleting and re-adding it:

1. **Settings → Devices & services → ESC/POS Thermal Printer**
2. Click your printer, then **Reconfigure** (in the three-dot menu of the integration entry)
3. Enter the new connection details

The entry keeps its identity, so entities, automations, blueprints, and device actions keep working. Reconfigure is for *connection* settings; print settings (profile, codepage, line width, timeouts, etc.) live under **Configure** (the options flow) as documented above. Note: USB and Bluetooth reconfiguration must point at the *same physical printer*. Re-pointing at a different device is rejected; add a new entry for a new printer.
