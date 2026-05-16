# Printing Images

Thermal printers are a 1-bit (black or white) medium. They love crisp line art, logos, QR codes, and high-contrast graphics; they tolerate photos when you give them a little help. This page covers every input source, every processing option, and the reliability knobs added for issues [#45](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/45) and [#43](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/43).

If you just want to print a file from disk, jump to [Local file](#local-file). If you're hitting buffer overruns, jump to [Reliability & speed](#reliability--speed).

## Overview

What works well:

- **Logos, badges, line art, QR codes.** Sharp black-on-white shapes print beautifully.
- **High-contrast photos with autocontrast + Floyd–Steinberg dither.** Faces and product shots come out recognizable.

What looks bad and how to fix it:

- **Faded photos** — turn on `autocontrast: true`.
- **Muddy logos with dotted edges** — switch from default dithering to `dither: threshold`.
- **Garbled output, freezes, or printed gibberish after the image** — see [Reliability & speed](#reliability--speed).
- **Sideways phone photos** — EXIF orientation is corrected automatically; you can additionally set `rotation: 90/180/270`.

## Image sources

The `image` field accepts any of these forms. The integration auto-detects which.

### Local file

A path on the Home Assistant filesystem. The integration **enforces**
HA's `allowlist_external_dirs` — paths outside it are rejected with
`HomeAssistantError`. Symlinks are dereferenced during validation (a
`.png` symlink pointing outside the allowlist is also rejected) and
the file is opened with `O_NOFOLLOW` to defeat TOCTOU swaps. If you
have automations that rely on reading from arbitrary host paths, add
those directories to `homeassistant: allowlist_external_dirs:` in
`configuration.yaml`.

```yaml
service: escpos_printer.print_image
data:
  image: /config/www/logo.png
```

### URL (HTTP / HTTPS)

```yaml
service: escpos_printer.print_image
data:
  image: https://your.host.tld/receipt.png
```

URL validation enforces:

- Scheme `http` or `https` only; default ports (80/443) only; no
  embedded credentials (`https://user:pass@host/` is rejected); no
  IDN/punycode hostnames.
- Hostname is resolved via `getaddrinfo`; the request is **refused if
  any resolved address is private, loopback, link-local, reserved,
  multicast, or unspecified**. That includes `127.0.0.1`, `::1`,
  RFC1918 ranges (`10.x`, `192.168.x`, `172.16.x`), and
  `169.254.169.254` (cloud metadata).
- Redirects are followed manually (max 5); every redirect target is
  re-validated against the rules above.

Max download size is 10 MB; the body is streamed and the read aborts
mid-stream when the cap is hit. `Content-Length` is checked before
reading. Fetches use HA's pooled httpx client (no per-request TLS
handshake cost) and fall back to HA's pooled aiohttp session only on
`ImportError` (not on HTTP errors).

### Camera entity

Prints a live snapshot from any `camera.<id>` entity. Pair with an
automation that triggers on a doorbell / motion event.

```yaml
service: escpos_printer.print_image
data:
  image: camera.front_door
```

**Permission check.** When the caller is a non-admin HA user, the
integration verifies the user has `POLICY_READ` on the named camera
before fetching. Users who can't view the camera in the frontend
receive `Unauthorized` (HTTP 403). Admin users bypass entity
permissions by design — that's HA's auth model, not specific to this
integration. Internal/automation calls without a `user_id` (the
common case) are unrestricted.

Full automation example:

```yaml
alias: Print snapshot when someone rings the bell
triggers:
  - trigger: state
    entity_id: binary_sensor.doorbell
    to: "on"
actions:
  - service: escpos_printer.print_image
    data:
      image: camera.front_door
      image_width: 384
      dither: floyd-steinberg
      autocontrast: true
      feed: 2
      cut: full
```

### Image entity

Any HA `image.<id>` entity — weather maps, generated charts, ML overlays, etc.

```yaml
service: escpos_printer.print_image
data:
  image: image.weather_radar
```

### Base64 data URI

Inline image bytes. Useful for webhooks, AppDaemon, or templates that
build images on the fly. Format: RFC 2397
(`data:image/<subtype>;base64,...`).

```yaml
service: escpos_printer.print_image
data:
  image: "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAA..."
```

Supported subtypes: `png`, `jpeg`, `jpg`, `gif`, `bmp`, `tiff`, `webp`
(SVG is **not** accepted; Pillow doesn't ship an SVG decoder and the
XML attack surface isn't worth it). The 10 MB cap applies to the
**decoded** bytes; the base64 string itself is also length-capped
before regex/decoding so a 200 MB string can't OOM the process.

### Jinja template

The `image` field is rendered as a template when it contains `{{` or
`{%`. That means you can pick a daily logo, pull a URL from a sensor,
or compute a path from a date. Templates are honored by both the
`escpos_printer.print_image` service and the `notify.<printer>` /
`escpos_printer.print_message` action's `image` field.

```yaml
service: escpos_printer.print_image
data:
  image: "/config/www/daily/{{ now().strftime('%Y-%m-%d') }}.png"
```

```yaml
service: escpos_printer.print_image
data:
  image: "{{ states('input_text.current_logo_url') }}"
```

## Processing options

Every option in one place.

| Option           | Default            | Description                                                                                                            |
|------------------|--------------------|------------------------------------------------------------------------------------------------------------------------|
| `image_width`    | profile max / 512  | Target width in pixels. Aspect ratio preserved. Never upscales.                                                        |
| `rotation`       | `0`                | Degrees clockwise: `0`, `90`, `180`, `270`. EXIF orientation is fixed before this is applied.                          |
| `dither`         | `floyd-steinberg`  | B&W conversion mode. `none` / `threshold` are alternatives.                                                            |
| `threshold`      | `128`              | Threshold value (1–254). Only used when `dither: threshold`.                                                           |
| `impl`           | reliability profile | python-escpos image command. See [Implementation selector](#implementation-selector).                                 |
| `center`         | `false`            | Horizontally center the image within the printer's paper width.                                                        |
| `align`          | printer's `default_align` | `left` / `center` / `right` — alignment of the image block on the page.                                          |
| `autocontrast`   | `false`            | Stretch the input's dynamic range before B&W conversion. Boost for photos.                                             |
| `invert`         | `false`            | Swap black and white. Useful for white-on-black source art or dark-mode logos.                                         |
| `mirror`         | `false`            | Flip horizontally. Useful for receipt-window displays read through the back of the paper.                              |
| `auto_resize`    | `false`            | Accept source images up to 40 MB and downscale before processing. Enable for iPhone HEIC / high-res cameras.           |
| `fallback_image` | unset              | Optional second source to try if the primary fails (camera unavailable, URL down, file missing).                       |
| `high_density`   | `true`             | Print in high vertical + horizontal density. Disable for stretched, faster output.                                     |
| `fragment_height`| reliability profile | Pixels per chunk when sending the image (issue #45). Smaller → safer, larger → faster. Step must be a multiple of 16. |
| `chunk_delay_ms` | reliability profile | Inter-chunk sleep (issue #43). Default depends on the printer's profile and transport. Raise if the printer freezes.  |
| `cut`            | printer's `default_cut` | `none` / `partial` / `full` after printing                                                                       |
| `feed`           | `0`                | Lines to feed after printing (0–50)                                                                                    |

### Reliability profile

Pick one in the integration's **Options** flow. Each profile sets sensible defaults for `fragment_height`, `chunk_delay_ms`, and `impl`; service-call options always override.

| Profile          | `fragment_height` | `chunk_delay_ms` | `impl`           | Use for                                  |
|------------------|-------------------|------------------|------------------|------------------------------------------|
| Auto             | (transport default) | (transport default) | `bitImageRaster` | Default — no preset                    |
| Fast LAN         | 512               | 0                | `bitImageRaster` | Epson TM-T20/T88 on Ethernet             |
| Balanced         | 256               | 20               | `bitImageRaster` | Most USB and Star TSP printers           |
| Conservative     | 128               | 100              | `bitImageRaster` | Cheap POS-58 / POS-80 clones             |
| Bluetooth-safe   | 128               | 150              | `bitImageRaster` | Slow SPP printers (default for BT entries) |

### Supported formats

PNG, JPEG, GIF, BMP, TIFF, WebP out of the box. **HEIC / HEIF / AVIF** are unlocked when `pillow-heif` is installed (`pip install pillow-heif` in the HA container). iPhone-fed camera proxies emit HEIC natively — installing `pillow-heif` removes the "image too large / wrong format" friction.

SVG is **not** supported (no sandboxed renderer ships with the integration; XML parsing is an attack surface).

### Recipe: crisp logo print

```yaml
service: escpos_printer.print_image
data:
  image: /config/www/logo.png
  image_width: 384
  dither: threshold
  threshold: 140
  center: true
  feed: 1
  cut: full
```

### Recipe: photo print

```yaml
service: escpos_printer.print_image
data:
  image: camera.living_room
  dither: floyd-steinberg
  autocontrast: true
  rotation: 0
  feed: 2
  cut: full
```

### Recipe: rotated label

```yaml
service: escpos_printer.print_image
data:
  image: /config/www/label.png
  rotation: 90
  image_width: 200
```

### Recipe: doorbell snapshot with fallback

```yaml
service: escpos_printer.print_image
data:
  image: camera.front_door
  fallback_image: /config/www/doorbell_placeholder.png
  auto_resize: true
  autocontrast: true
  feed: 2
  cut: full
```

## Convenience services

When the source type is fixed, use the focused services for a friendlier UI (entity pickers, etc.) — they all funnel into the same pipeline as `print_image`.

| Service                          | Source field    | Selector       |
|----------------------------------|-----------------|----------------|
| `escpos_printer.print_camera_snapshot` | `camera_entity` | camera entity  |
| `escpos_printer.print_image_entity`    | `image_entity`  | image entity   |
| `escpos_printer.print_image_url`       | `url`           | plain text     |

## Preview without printing

`escpos_printer.preview_image` runs the **exact same** processing pipeline as `print_image` and writes the resulting 1-bit PNG to disk — without burning paper. Use it from Developer Tools → Services to tune `dither` / `threshold` / `image_width` in seconds.

```yaml
service: escpos_printer.preview_image
data:
  image: camera.living_room
  output_path: /config/www/last_preview.png
  dither: floyd-steinberg
  autocontrast: true
```

The service returns `{path, width, height, slice_count}` so you can chain a notification:

```yaml
- service: escpos_printer.preview_image
  data:
    image: camera.living_room
    output_path: /config/www/preview.png
  response_variable: preview
- service: notify.persistent_notification
  data:
    message: "Preview ready ({{ preview.width }}x{{ preview.height }})"
```

If `output_path` is omitted, the preview lands at `/tmp/escpos_preview_<entry>.png`.

## Calibration print

`escpos_printer.calibration_print` prints a one-page calibration sheet: a pixel ruler plus a horizontal-gradient strip at several threshold values. Look for the strip where black-to-white is sharpest — that's the threshold to use with `dither: threshold` for line art.

## `image_*` prefix on the notify entity

The `escpos_printer.print_message` / `notify.<printer>` action accepts both the prefixed (`image_dither`) and unprefixed (`dither`) forms for image-only options. Use whichever you remember; prefixed wins if both are set. The prefix is still required for fields that collide with text-side options (`image_align`, `image_high_density`).

## Reliability & speed

Issue [#45](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/45) reports that very tall images can overrun the printer's input buffer — the printer freezes, then dumps the remaining image bytes as garbled characters at the start of the next print. Issue [#43](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/43) asked for a way to throttle image printing on cheap clones. Both are addressed by chunked transmission with an optional inter-chunk sleep.

How it works: the integration crops the processed image into horizontal slices of `fragment_height` pixels and sends each slice as its own ESC/POS image command, sleeping `chunk_delay_ms` milliseconds between slices.

**Per-printer defaults come from the Reliability profile** (set in the integration's Options flow). Network/USB printers default to the **Auto** profile (transport defaults: 256-px slices, 0-ms delay); Bluetooth entries default to **Bluetooth-safe** (128-px slices, 150-ms delay). Service-call values override the profile.

Suggested starting points:

| Printer class             | `fragment_height` | `chunk_delay_ms` |
|---------------------------|-------------------|------------------|
| Epson TM-T20/T88 (LAN)    | 512               | 0–20             |
| Star TSP100/TSP650        | 256               | 20               |
| Generic POS-58 / POS-80   | 128–256           | 50–100           |
| Cheap Bluetooth thermal   | 128               | 100–200          |

Symptoms-to-knob mapping:

- **Garbled characters at the start of the next print** → lower `fragment_height` *and* raise `chunk_delay_ms`.
- **Print pauses mid-image then resumes garbled** → raise `chunk_delay_ms` first.
- **Prints are too fast / motor stalls** → raise `chunk_delay_ms` to throttle.
- **Prints are reliable but slow** → raise `fragment_height` and drop `chunk_delay_ms` to 0.

## Implementation selector

`impl` controls which ESC/POS image command python-escpos emits:

- `bitImageRaster` (default) — `GS v 0`. Best default for
  Epson-compatible printers.
- `graphics` — `GS ( L`. Newer ESC/POS graphics block. Try this if
  `bitImageRaster` prints stretched or garbled.
- `bitImageColumn` — `ESC *`. Older column-mode command. Try this if
  the chosen impl looks misaligned on a generic POS-58 / POS-80 clone.

If a printer prints text fine but images look wrong, cycling through
`impl` is the first thing to try — it's a pure protocol selector with
no other side effects.

If the installed python-escpos version doesn't accept the chosen
`impl` keyword, the integration silently falls back to a kwarg-less
`printer.image()` call (which python-escpos picks an implementation
for). Check the integration log for `Image slice ... failed` if you
suspect the fallback fired.

## Notify entity integration

The notify entity's `print_message` service accepts an optional
`image` (plus `image_*` parameters mirroring `print_image`). Text and
image print as a **single uninterrupted receipt** under one printer
lock acquisition — concurrent callers can no longer interleave between
the text and image halves. Image bytes are resolved (URL fetch, file
read, camera snapshot) *before* the lock is taken, so a slow camera
doesn't monopolize the printer queue.

```yaml
service: notify.send_message
target:
  entity_id: notify.esc_pos_printer_192_168_1_50_9100
data:
  message: "Front door – 14:23"
  data:
    image: camera.front_door
    image_dither: floyd-steinberg
    image_autocontrast: true
```

Or the entity-service form (more parameters available):

```yaml
service: escpos_printer.print_message
target:
  entity_id: notify.esc_pos_printer_192_168_1_50_9100
data:
  title: "Front door"
  message: "Motion at 14:23"
  bold: true
  image: camera.front_door
  image_width: 384
  image_dither: floyd-steinberg
  image_autocontrast: true
  feed: 2
  cut: full
```

## Troubleshooting

| Symptom                                                | Likely cause / fix                                                                                                                                       |
|--------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------|
| `Image too large (max 10MB)`                           | Pre-resize the image before sending, or convert to a more efficient format (PNG → JPEG for photos).                                                      |
| `Image file does not exist or is not a regular file`   | Path typo, or HA can't see the file. Confirm the file exists *inside the HA container/VM*, not just on your laptop.                                      |
| `Only data:image/...;base64,...` error                 | Your base64 string is missing the `data:image/<subtype>;base64,` prefix. Wrap it like that.                                                              |
| `Failed to fetch camera image`                         | The camera entity is unavailable or slow. Snapshot timeout is 10 s; check the camera state in Developer Tools.                                           |
| `Expected entity_id in domain 'camera'`                | You passed something like `cam.front_door` or `camera.` (empty). Use the full `camera.<id>` form.                                                        |
| `impl must be one of ['bitImageColumn', ...]`          | Typo in `impl` value. Allowed: `bitImageRaster`, `graphics`, `bitImageColumn`.                                                                           |
| Printer freezes, then next print shows garbage chars   | Classic buffer overrun. Lower `fragment_height` (try 128) and raise `chunk_delay_ms` (try 100). See [Reliability & speed](#reliability--speed).          |
| Image prints stretched or in stripes                   | Try `impl: graphics` or `impl: bitImageColumn`. If it's a USB Epson, leave `impl: bitImageRaster` and check the cable.                                   |
| Logo looks muddy with dotted edges                     | Switch from `dither: floyd-steinberg` (default) to `dither: threshold` and tune `threshold` between 100–180.                                             |
| Photo prints almost all black or all white             | Turn on `autocontrast: true`. If still extreme, try `dither: threshold` with a value near the image's average brightness.                                |
| Image is sideways (phone photos)                       | EXIF orientation should auto-correct. If your image lacks EXIF, use `rotation: 90` / `180` / `270`.                                                      |
| `Failed to download image: ...`                        | URL is wrong, requires auth, or your HA host can't reach it. Test the URL with `curl` from the host first.                                               |
| Image command works in `print_image` but not `notify`  | Notify uses `image_*`-prefixed parameter names (e.g. `image_dither`, not `dither`). See [Notify entity integration](#notify-entity-integration).         |
