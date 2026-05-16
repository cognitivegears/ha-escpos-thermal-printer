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

## escpos_printer.print_image

> See the [Images guide](images.md) for end-to-end examples, source forms, and recipes.

| Parameter | Type | Description |
|-----------|------|-------------|
| image | string | Source (required). URL, local path, `camera.<id>`, `image.<id>`, `data:image/...;base64,...`, or a Jinja template producing any of these. |
| high_density | boolean | High-density mode (default true) |
| align | string | `left`, `center`, `right` |
| image_width | int | Target width in pixels. Defaults to the printer profile's max width (or 512 if unknown). Never upscales. |
| rotation | int | `0`, `90`, `180`, `270` (clockwise). EXIF orientation is auto-corrected. |
| dither | string | `floyd-steinberg` (default), `none`, or `threshold` |
| threshold | int | 1–254. Only used when `dither: threshold` (default 128). |
| impl | string | `bitImageRaster` (default), `graphics`, or `bitImageColumn` |
| center | boolean | Horizontally center the image on the paper |
| autocontrast | boolean | Stretch contrast before B&W conversion (good for photos) |
| fragment_height | int | Pixels per chunk when sending the image (default 256, range 16–1024). |
| chunk_delay_ms | int | Sleep between chunks in ms (default 50, range 0–5000). Increase if you see buffer overruns. |
| cut | string | `none`, `partial`, `full` |
| feed | int | Lines to feed (0–10) |

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
