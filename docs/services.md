# Services

The integration registers these services. All accept a `target` parameter for device targeting (see [multi-printer.md](multi-printer.md)).

## escpos_printer.print_text

Print raw text using the configured codepage. No transcoding.

| Parameter | Type | Description |
|-----------|------|-------------|
| text | string | Text to print (required) |
| align | string | `left`, `center`, `right` |
| bold | boolean | Bold text |
| underline | string | `none`, `single`, `double` |
| width | string\|int | `normal`, `double`, `triple`, or 1–8 |
| height | string\|int | `normal`, `double`, `triple`, or 1–8 |
| encoding | string | Override codepage |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–10) |

## escpos_printer.print_text_utf8

Same as `print_text` but auto-converts UTF-8 characters to printer-compatible encoding (curly quotes → straight, em-dash → `--`, accented letters simplified when needed). Does not accept the `encoding` parameter.

## escpos_printer.print_message

Entity service for the notify platform. Targets a notify entity and supports all text formatting plus optional UTF-8 transcoding via `utf8: true`, plus an optional image. Same parameters as `print_text` plus:

| Parameter | Type | Description |
|-----------|------|-------------|
| message | string | Text (required) |
| title | string | Printed before the message |
| utf8 | boolean | Enable UTF-8 transcoding |
| image | string | Optional image source — same forms as `print_image`. See [Images guide](images.md). |
| image_width | int | Target image width (pixels) |
| image_align | string | `left`, `center`, `right` |
| image_dither | string | `floyd-steinberg`, `none`, `threshold` |
| image_rotation | int | `0`, `90`, `180`, `270` |
| image_impl | string | `bitImageRaster`, `graphics`, `bitImageColumn` |
| image_center | boolean | Horizontally center the image |
| image_autocontrast | boolean | Stretch contrast before B&W conversion |
| image_threshold | int | 1–254 (used with `image_dither: threshold`) |
| image_fragment_height | int | Pixels per chunk |
| image_chunk_delay_ms | int | Sleep between chunks |

## escpos_printer.print_qr

| Parameter | Type | Description |
|-----------|------|-------------|
| data | string | Data to encode (required) |
| size | int | Module size 1–16 (default 3) |
| ec | string | Error correction: `L`, `M`, `Q`, `H` |
| align | string | `left`, `center`, `right` |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–10) |

## escpos_printer.print_barcode

Supported types: `EAN13`, `EAN8`, `UPC-A`, `UPC-E`, `CODE39`, `CODE93`, `CODE128`, `ITF`, `CODABAR`.

| Parameter | Type | Description |
|-----------|------|-------------|
| code | string | Barcode data (required) |
| bc | string | Barcode type (required) |
| height | int | Height in dots (1–255) |
| width | int | Width multiplier (2–6) |
| pos | string | Text position: `ABOVE`, `BELOW`, `BOTH`, `OFF` |
| font | string | Text font: `A`, `B` |
| align_ct | boolean | Center the barcode |
| check | boolean | Validate checksum |
| force_software | string | Rendering mode |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–10) |

## Image services

The integration ships six image-printing services. They all share the same image-processing options (rotation, mirror, threshold, dither, etc.) and route through the same backend pipeline — the only difference is the source field and which UI selector is used.

| Service | Source field | When to use |
|---------|--------------|-------------|
| `escpos_printer.print_image` | `image` (template) | Generic / power-user. Accepts any source form — URL, file path, `camera.<id>`, `image.<id>`, base64 data URI, or a Jinja template producing any of those. **Existing automations using a literal URL or path keep working unchanged.** |
| `escpos_printer.print_image_url` | `url` (text) | Print from an HTTP(S) URL. SSRF-aware — private, loopback, and link-local addresses are refused. |
| `escpos_printer.print_image_path` | `path` (text) | Print a local file. The path must lie inside `allowlist_external_dirs` (typically `/config` or `/media`). |
| `escpos_printer.print_camera_snapshot` | `camera_entity` (camera entity picker) | Print a live snapshot from a camera entity. |
| `escpos_printer.print_image_entity` | `image_entity` (image entity picker) | Print the current frame from an HA `image` entity (weather radar, ML overlay, generated chart). |
| `escpos_printer.preview_image` | `image` (template) | Run the image pipeline and write the 1-bit PNG to disk **without** printing. Returns `{path, width, height, slice_count}`. |

> See the [Images guide](images.md) for end-to-end examples, source-form security notes, and tuning recipes.

### Shared image-processing options

Every image service accepts the same option set. Rarely-used reliability knobs are marked **advanced** — they only appear in the HA UI form when Home Assistant's advanced mode is on, but YAML scripts can pass them any time.

| Parameter | Type | Description |
|-----------|------|-------------|
| image_width | int | Target width in pixels. Defaults to the printer profile's max width (or 512 if unknown). Never upscales. Range 16–2048. |
| rotation | int | `0`, `90`, `180`, `270` (clockwise). EXIF orientation is auto-corrected. Default `0`. |
| dither | string | `floyd-steinberg` (default), `none`, or `threshold`. |
| threshold | int | 1–254 (default 128). Only used when `dither: threshold`. 100-180 typical for line art. |
| mirror | boolean | Flip the image left-to-right before printing. Default `false`. |
| invert | boolean | Swap black/white before B&W conversion. Useful for dark-mode source images. Default `false`. |
| autocontrast | boolean | Stretch contrast before B&W conversion (helps photos). Default `false` (`true` for `print_camera_snapshot`). |
| auto_resize | boolean | Allow source images up to 40 MB and downscale before processing. Default `false` (`true` for `print_image_url`, `print_image_path`, `print_camera_snapshot`). |
| align | string | `left`, `center`, `right`. |
| center | boolean | Horizontally center the image on the paper. Default `false`. |
| high_density | boolean | High-density printing mode. Default `true`. |
| cut | string | `none`, `partial`, `full`. Defaults to the printer's configured cut mode. |
| feed | int | Lines to feed after printing (0–50). Defaults vary per service (0 for generic, 1 for URL/path/image-entity, 2 for camera snapshot). |
| impl | string | **advanced.** `bitImageRaster`, `graphics`, or `bitImageColumn`. Leave unset to honor the printer's Reliability profile. |
| fragment_height | int | **advanced.** Rows per chunk when sending the image (range 16–1024). Leave unset to honor the printer's Reliability profile. |
| chunk_delay_ms | int | **advanced.** Sleep between chunks in ms (range 0–5000). Leave unset to honor the printer's Reliability profile (0 ms on Network/USB, 50 ms on Bluetooth). |
| fallback_image | string | **advanced.** Optional URL / path / camera entity to print if the primary source fails to resolve. |

`preview_image` additionally accepts `output_path` (where to save the PNG; defaults to `/tmp/escpos_preview_<entry>.png`) and omits the printer-communication knobs (`high_density`, `impl`, `fragment_height`, `chunk_delay_ms`, `center`, `cut`, `feed`) because they have no effect on the file written to disk.

Tips: pick `dither: threshold` for crisp logos/text, `dither: floyd-steinberg` + `autocontrast: true` for photos. If your printer freezes or dumps characters on tall images, lower `fragment_height` or raise `chunk_delay_ms`.

## escpos_printer.feed

| Parameter | Type | Description |
|-----------|------|-------------|
| lines | int | Lines to feed 1–10 (required) |

## escpos_printer.cut

| Parameter | Type | Description |
|-----------|------|-------------|
| mode | string | `full` or `partial` (required) |

## escpos_printer.beep

If the printer supports it.

| Parameter | Type | Description |
|-----------|------|-------------|
| times | int | Number of beeps (default 2) |
| duration | int | Beep duration (default 4) |
