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
| feed | int | Lines to feed after printing (0–50). Default depends on the service: `print_image` = `0`; `print_image_url` / `print_image_path` / `print_image_entity` = `1`; `print_camera_snapshot` = `2`; `calibration_print` = `2`. The focused services pick friendlier defaults than `print_image` because their typical use-case prints once and you want a paper buffer for tearing off cleanly. |
| impl | string | **advanced.** `bitImageRaster`, `graphics`, or `bitImageColumn`. Leave unset to honor the printer's Reliability profile. |
| fragment_height | int | **advanced.** Rows per chunk when sending the image (range 16–1024). Leave unset to honor the printer's Reliability profile. |
| chunk_delay_ms | int | **advanced.** Sleep between chunks in ms (range 0–5000). Leave unset to honor the printer's Reliability profile (0 ms on Network/USB, 50 ms on Bluetooth). |
| fallback_image | string | **advanced.** Optional URL / path / camera entity to print if the primary source fails to resolve. |

`preview_image` additionally accepts `output_path` (where to save the PNG; defaults to `/tmp/escpos_preview_<entry>.png`) and omits the printer-communication knobs (`high_density`, `impl`, `fragment_height`, `chunk_delay_ms`, `center`, `cut`, `feed`) because they have no effect on the file written to disk.

Tips: pick `dither: threshold` for crisp logos/text, `dither: floyd-steinberg` + `autocontrast: true` for photos. If your printer freezes or dumps characters on tall images, lower `fragment_height` or raise `chunk_delay_ms`.

## Text-effects services

For boxes, multi-column tables, and custom-font / rotated text, see
the [Text effects guide](text-effects.md) for the full reference,
border-style table, bundled-font notes, and worked examples. Short
summaries below.

### escpos_printer.print_box

Wrap text in a printable border (cp437 single/double, ASCII, asterisk, hash, or no border).

| Parameter | Type | Description |
|-----------|------|-------------|
| text | string | Text to wrap (required) |
| style | string | `auto` (default), `single`, `double`, `ascii`, `asterisk`, `hash`, `none` |
| padding | int | Blank rows above/below content (0–4) |
| align | string | `left`, `center`, `right` |
| total_width | int | Total printed width incl. borders (3–200); defaults to printer line width |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–50) |

### escpos_printer.print_table

Multi-column rows with optional borders, header, and inner separators.

| Parameter | Type | Description |
|-----------|------|-------------|
| rows | list of lists of strings | The grid (required, up to 200×12) |
| style | string | Same options as `print_box` |
| column_widths | list of ints | Per-column widths in characters |
| column_aligns | list of strings | Per-column alignment (`left`/`center`/`right`) |
| header | boolean | Treat first row as header (rule below it) |
| row_separators | boolean | Insert a horizontal rule between every body row |
| total_width | int | Total printed width (3–200); defaults to printer line width |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–50) |

### escpos_printer.print_text_image

Render text to a bitmap with a TTF/OTF font, optionally rotated, then print through the image pipeline. Useful for headers, banners, sideways labels, and non-codepage glyphs.

| Parameter | Type | Description |
|-----------|------|-------------|
| text | string | Text to render (required) |
| font | string | Bundled font: `dejavu_mono` (default), `dejavu_sans`, `dejavu_serif` |
| font_path | string | Optional `.ttf` / `.otf` path. Drop files in `/config/fonts/` (auto-trusted), or use a path under `allowlist_external_dirs`. Overrides `font`. |
| font_size | int | Point size 8–96 (default 16) |
| line_spacing | number | Line-height multiplier 1.0–3.0 (default 1.1) |
| align | string | `left`, `center`, `right` (text canvas alignment) |
| rotation | int | `0`, `90`, `180`, `270` (clockwise; applied to canvas before binarisation) |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–50) |
| `image_*` knobs (advanced) | — | `image_width`, `image_dither`, `image_threshold`, `image_impl`, `image_center`, `image_autocontrast`, `image_invert`, `image_mirror`, `image_high_density`, `image_fragment_height`, `image_chunk_delay_ms` — same names and defaults as `print_message`'s image-pipeline knobs |

### escpos_printer.print_separator

Print a single decorative rule by repeating one character to fill the line width.

| Parameter | Type | Description |
|-----------|------|-------------|
| char | string | Single printable ASCII character to repeat (default `-`) |
| width | int | Repeat count (1–200); defaults to the printer's line width |
| repeat | int | Number of consecutive lines (1–10, default 1). Use `2` for a double rule. |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–50) |

### escpos_printer.print_kvtable

Two-column label/value table for receipt totals, sensor readings, ingredient lists.

| Parameter | Type | Description |
|-----------|------|-------------|
| items | list of `[label, value]` pairs | The grid (required, up to 200 rows) |
| style | string | Same options as `print_table`; default `none` (borderless) |
| total_width | int | Total printed width (3–200); defaults to printer line width |
| label_width | int | Characters reserved for the label column; auto-sized from the longest label up to ~60% of `total_width` |
| value_align | string | `left`, `center`, `right` (default `right`) |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–50) |

### escpos_printer.preview_box

Render a `print_box` layout to a `.txt` file *without* printing. Returns the output path and rendered size so automations can chain a notification or inspect the layout. Has `supports_response: only` — call with `return_response: true`.

| Parameter | Type | Description |
|-----------|------|-------------|
| text, style, padding, align, total_width | — | Same fields as `print_box`. `cut` and `feed` are deliberately omitted — a text file has no paper. |
| output_path | string | Where to save the rendered text. **Must be inside the system temp directory (typically `/tmp`)** — non-admin HA users could otherwise overwrite arbitrary files in `allowlist_external_dirs`. Defaults to `/tmp/escpos_preview_box_<entry>.txt`. To persist the preview elsewhere, copy the returned `path` in a follow-up automation step. |

Response shape: `{path, width, line_count, codepage}`.

### escpos_printer.preview_table

Render a `print_table` layout to a `.txt` file *without* printing. Same contract as `preview_box`.

| Parameter | Type | Description |
|-----------|------|-------------|
| rows, style, column_widths, column_aligns, header, row_separators, total_width | — | Same fields as `print_table`. `cut` and `feed` are deliberately omitted — a text file has no paper. |
| output_path | string | Where to save the rendered text. **Must be inside the system temp directory (typically `/tmp`)** — non-admin HA users could otherwise overwrite arbitrary files in `allowlist_external_dirs`. Defaults to `/tmp/escpos_preview_table_<entry>.txt`. To persist the preview elsewhere, copy the returned `path` in a follow-up automation step. |

Response shape: `{path, width, line_count, codepage}`.

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
