# Text Effects: Boxes, Tables, and Custom-Font Text

## Your first receipt (30 seconds)

Paste this in **Developer Tools → Actions** and hit *Perform action*. If
you only have one printer configured, no `target:` is needed.

```yaml
action: escpos_printer.print_box
data:
  text: "Hello from Home Assistant!"
  style: auto
  align: center
  padding: 1
  feed: 1
```

That's it — a bordered card on paper. Read on for tables, key/value
totals, custom fonts, and the previewing workflow that lets you iterate
without burning a roll of paper.

## What's in this guide

This integration ships three services for laying out text beyond the
plain `print_text` formatting (bold / underline / multiplier sizes):

| Service | What it does |
|---------|--------------|
| `escpos_printer.print_box` | Wraps text in a printable border (cp437 single/double, ASCII, asterisk, hash). |
| `escpos_printer.print_table` | Multi-column rows for receipt-style layouts, optional header and inner separators. |
| `escpos_printer.print_text_image` | Renders text to a bitmap with a bundled or user-supplied TTF/OTF font; supports 0/90/180/270° rotation and any point size. |

`print_box` and `print_table` build a plain text layout and ride on
the printer's text mode — they're fast and respect the configured
codepage. `print_text_image` rasterizes the text and prints through
the same pipeline as `print_image`, so it works with **any** font /
size / rotation but takes longer than text mode.

> **Heads-up on non-ASCII text.** `print_box` and `print_table` use one
> character cell per column. CJK characters, emoji, and combining marks
> may misalign on narrow printers — see [CJK / wide-character content](#cjk)
> at the bottom of this guide. For mixed-script content, prefer
> `print_text_image` (which measures actual glyph widths in pixels).

## Border styles

Both `print_box` and `print_table` accept a `style` parameter:

| Style | Looks like | Best for |
|-------|------------|----------|
| `auto` *(default)* | Adapts to codepage — single on cp437/cp850/cp852/cp858/cp860/cp863/cp865/cp866, ASCII elsewhere. | Most users; the integration picks the right glyphs for your printer. |
| `single` | `┌─┐` `│ │` `└─┘` | Receipts with cp437-family codepage. |
| `double` | `╔═╗` `║ ║` `╚═╝` | Heavier, more visually striking. |
| `ascii`  | `+-+` `\| \|` `+-+` | Any codepage; very compatible. |
| `asterisk` | `***` `* *` `***` | Decorative. |
| `hash`   | `###` `# #` `###` | Decorative. |
| `none` | (no border characters) | Borderless multi-column grids. |

**How `auto` works.** The resolver probes whether the configured
codepage can natively encode the cp437 box-drawing block. When it
can, you get crisp single-line glyphs (`┌─┐`); when it can't, you
get ASCII (`+-+`) so the printed layout still aligns column-for-
column. If you explicitly pick `single` or `double` on a codepage
that doesn't support them, the existing UTF-8 transcoder substitutes
ASCII lookalikes (single-character replacements, so column widths
stay correct).

## `escpos_printer.print_box`

Wrap a block of text in a border.

### Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `device_id` | device / [device] | *(broadcast)* | Optional target. |
| `text` | string | *(required)* | Text to wrap. Supports newlines. Up to 10 000 chars. |
| `style` | enum | `auto` | One of `auto`, `single`, `double`, `ascii`, `asterisk`, `hash`, `none`. |
| `padding` | int | `0` | Blank rows added above and below the content (0-4). |
| `align` | enum | `left` | Text alignment inside the box (`left`, `center`, `right`). |
| `total_width` | int | printer `line_width` | Total printed width in characters, *including* borders (3-200). Defaults to the printer's configured line width. |
| `cut` | enum | printer default | `none`, `partial`, `full`. |
| `feed` | int | `0` | Lines to feed after printing (0-50). |

### Examples

A bordered title on a CP437 printer:

```yaml
action: escpos_printer.print_box
data:
  text: DAILY REPORT
  style: auto         # → single-line ┌─┐ on CP437
  padding: 1
  align: center
  feed: 1
```

```text
┌──────────────────────────────────────────────┐
│                                              │
│                 DAILY REPORT                 │
│                                              │
└──────────────────────────────────────────────┘
```

A portable ASCII box for codepages that don't support drawing glyphs:

```yaml
action: escpos_printer.print_box
data:
  text: "Sensor alert: garage door has been open for 30 minutes."
  style: ascii
  total_width: 32
```

```text
+------------------------------+
|Sensor alert: garage door has |
|been open for 30 minutes.     |
+------------------------------+
```

Decorative banner:

```yaml
action: escpos_printer.print_box
data:
  text: "  HAPPY BIRTHDAY  "
  style: asterisk
  align: center
  padding: 1
```

## `escpos_printer.print_table`

Multi-column rows. Each row is a list of cell strings. Cells that
exceed their column width word-wrap and the row grows to the tallest
cell.

### Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `device_id` | device / [device] | *(broadcast)* | Optional target. |
| `rows` | list of lists of strings | *(required)* | The grid. First row is the header when `header: true`. Up to 200 rows × 12 cols. |
| `style` | enum | `auto` | Same options as `print_box`. `none` gives a borderless aligned grid. |
| `column_widths` | list of ints | even split | Per-column character widths. Sum + (cols+1) separators must fit `total_width`. |
| `column_aligns` | list of enums | all `left` | Per-column alignment (`left`/`center`/`right`). |
| `header` | bool | `false` | Treat the first row as a header (rule below it). |
| `row_separators` | bool | `false` | Insert a horizontal rule between every body row. |
| `total_width` | int | printer `line_width` | Total printed width in characters including borders (3-200). |
| `cut` | enum | printer default | `none`, `partial`, `full`. |
| `feed` | int | `0` | Lines to feed (0-50). |

### Examples

Receipt-style table with header and per-column alignment:

```yaml
action: escpos_printer.print_table
data:
  rows:
    - ["Item", "Qty", "Price"]
    - ["Coffee", "2", "$6.00"]
    - ["Bagel", "1", "$3.50"]
    - ["Total", "", "$9.50"]
  style: single
  header: true
  column_widths: [28, 5, 9]
  column_aligns: ["left", "center", "right"]
  total_width: 48
  feed: 2
```

```text
┌────────────────────────────┬─────┬─────────┐
│Item                        │ Qty │    Price│
├────────────────────────────┼─────┼─────────┤
│Coffee                      │  2  │    $6.00│
│Bagel                       │  1  │    $3.50│
│Total                       │     │    $9.50│
└────────────────────────────┴─────┴─────────┘
```

Borderless aligned columns (great for itemized lines without the box):

```yaml
action: escpos_printer.print_table
data:
  rows:
    - ["Coffee x2",    "$6.00"]
    - ["Bagel",        "$3.50"]
    - ["Croissant",    "$4.25"]
    - ["TOTAL",       "$13.75"]
  style: none
  column_widths: [40, 7]
  column_aligns: ["left", "right"]
```

```text
Coffee x2                                  $6.00
Bagel                                      $3.50
Croissant                                  $4.25
TOTAL                                     $13.75
```

Row-by-row separators for emphasis:

```yaml
action: escpos_printer.print_table
data:
  rows:
    - ["Time",  "Event"]
    - ["08:14", "Door opened"]
    - ["08:32", "Motion in hallway"]
    - ["09:05", "Door closed"]
  style: double
  header: true
  row_separators: true
```

## `escpos_printer.print_text_image`

Render text to a PIL bitmap with a TrueType / OpenType font, optional
rotation, and any point size, then print it through the existing
image pipeline. Unlike `print_box` and `print_table`, the output is
an image — so the printer doesn't need to support the glyphs in its
codepage. Anything that renders in the font will print.

This is the path to use for:

- Receipts in a non-Latin script the printer doesn't have a codepage for.
- Large headers / banners (rotate 90° for sideways logos along the side of the receipt).
- Decorative fonts that aren't part of the printer's built-in set.

### Bundled fonts

Three fonts ship with the integration in
`custom_components/escpos_printer/fonts/`:

| Name | File | Best for |
|------|------|----------|
| `dejavu_mono` *(default)* | DejaVuSansMono.ttf | Receipts, tabular text, code. Monospaced; aligns predictably. |
| `dejavu_sans` | DejaVuSans.ttf | Headers, banners, anywhere a proportional font reads better. |
| `dejavu_serif` | DejaVuSerif.ttf | Elegant receipts, recipe cards, long-form text. Proportional with classic letterforms. |

All three are released under the permissive DejaVu license (public-domain
modifications on top of Bitstream Vera) — see the `fonts/LICENSE`
file and the repo-root `NOTICE`.

### User-supplied fonts

**The easiest way:** drop your `.ttf` / `.otf` files in
`/config/fonts/` and reference them directly. The integration
creates this directory on first setup and treats it as locally
trusted — no `configuration.yaml` edits needed.

```yaml
font_path: "/config/fonts/MyBrand-Bold.otf"
font_size: 36
```

For fonts that live anywhere else, the path must satisfy Home
Assistant's `allowlist_external_dirs` (typically `/config`,
`/media`, or `/share`). Add the parent directory to that list in
`configuration.yaml`:

```yaml
homeassistant:
  allowlist_external_dirs:
    - /share/fonts
```

When `font_path` is set, the bundled `font` field is ignored. Paths
are validated: extension is checked (`.ttf` / `.otf`), the file must
be a regular file (not a symlink target outside the trusted set),
and size is capped at 16 MB.

### Parameters

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `device_id` | device / [device] | *(broadcast)* | Optional target. |
| `text` | string | *(required)* | Text to render. Supports newlines (each newline starts a new line on the bitmap). Up to 10 000 chars. |
| `font` | enum | `dejavu_mono` | Bundled font — `dejavu_mono`, `dejavu_sans`, or `dejavu_serif`. Ignored when `font_path` is set. |
| `font_path` | string | *(unset)* | Optional path to a `.ttf` / `.otf` file inside `allowlist_external_dirs`. |
| `font_size` | int | `16` | Point size (8-96). |
| `line_spacing` | number | `1.1` | Multiplier on the font's natural line height (1.0-3.0). |
| `rotation` | enum | `0` | `0`, `90`, `180`, or `270` (clockwise). Applied to the rendered canvas before binarisation. |
| `align` | enum | `left` | Per-line alignment inside the canvas. |

The service also accepts every option from `print_image`, prefixed
with `image_` so they line up one-to-one with `print_message`'s
image-pipeline knobs: `image_width`, `image_dither`, `image_threshold`,
`image_impl`, `image_center`, `image_autocontrast`, `image_invert`,
`image_mirror`, `image_high_density`, `image_fragment_height`,
`image_chunk_delay_ms`. Plus the top-level `cut` and `feed`. See the
[Images guide](images.md) for what each one does. The two most
useful for text:

- `image_dither: threshold` + `image_threshold: 128` (default) — crisp
  text edges. Lower (e.g. `80`) prints "thicker"; higher (`160`) prints
  "thinner". Floyd-Steinberg dithering blurs single-pixel serifs, so
  threshold mode usually wins for text.
- `font_size` — use 24-36 for headers, 12-18 for body, 48+ for
  page-fillers. Larger sizes look better at high `image_width`
  values; 128 px wide at 48 pt produces visibly blocky glyphs.

### Examples

A large bold header:

```yaml
action: escpos_printer.print_text_image
data:
  text: HEADER
  font: dejavu_sans
  font_size: 48
  align: center
  feed: 1
```

A sideways line printed along the side of the page:

```yaml
action: escpos_printer.print_text_image
data:
  text: "← TEAR HERE"
  font: dejavu_mono
  font_size: 24
  rotation: 90
```

Multi-line announcement at a non-default font:

```yaml
action: escpos_printer.print_text_image
data:
  text: |
    Garage door
    has been OPEN
    for 30 minutes
  font_path: "/config/fonts/Anton-Regular.ttf"
  font_size: 32
  align: center
  feed: 2
```

Crisp ASCII art via dither:

```yaml
action: escpos_printer.print_text_image
data:
  text: |
        /\_/\
       ( o.o )
        > ^ <
  font: dejavu_mono
  font_size: 18
  image_dither: threshold
  image_threshold: 140
```

## `escpos_printer.print_separator`

A single decorative rule built by repeating one character across the
line width. Tiny but constantly useful — visually separates
sections of a multi-call receipt.

### Examples

Single rule (default `char: "-"`):

```yaml
action: escpos_printer.print_separator
```

Heavy double rule (`=` repeated, two consecutive lines):

```yaml
action: escpos_printer.print_separator
data:
  char: "="
  repeat: 2
```

Decorative asterisk banner:

```yaml
action: escpos_printer.print_separator
data:
  char: "*"
  width: 32
```

When to use `print_separator` vs. an empty `print_box`: separators
are faster (no border rendering), single-line, and great for
chaining between other services. Boxes are richer (alignment,
padding, multi-line) but heavier.

## `escpos_printer.print_kvtable`

A focused two-column service for **label / value** rows — receipt
totals, sensor readings, ingredient lists, settings recaps. Labels
left-align; values right-align by default (typical for totals).

Behind the scenes this builds on `print_table` with `header: false`
and two columns. Use it whenever you'd otherwise hand-craft a 2-col
table.

### Examples

Receipt totals (borderless, right-aligned values):

```yaml
action: escpos_printer.print_kvtable
data:
  items:
    - ["Subtotal", "$10.00"]
    - ["Tax",      "$0.80"]
    - ["Total",    "$10.80"]
```

Result on a 48-column printer:

```text
Subtotal                                 $10.00
Tax                                       $0.80
Total                                    $10.80
```

Sensor readings (`value_align: left` for "name: value" style):

```yaml
action: escpos_printer.print_kvtable
data:
  items:
    - ["Temperature", "21.4°C"]
    - ["Humidity",    "45%"]
    - ["Pressure",    "1013 hPa"]
  value_align: left
  label_width: 14
```

Bordered totals (with `style: single`):

```yaml
action: escpos_printer.print_kvtable
data:
  items:
    - ["Subtotal", "$10.00"]
    - ["Total",    "$10.80"]
  style: single
  total_width: 28
```

## Previewing without paper

The `preview_box` and `preview_table` services run the same layout
pipeline as their `print_*` counterparts but write the rendered text
to a `.txt` file instead of sending it to the printer. Use them when
designing a layout — iterate on column widths or padding without
burning a roll.

Both services have `supports_response: only`. In Developer Tools →
**Actions**, set "Return response data" to "Show" so you see the
output path and dimensions.

```yaml
action: escpos_printer.preview_table
data:
  rows:
    - ["Item",  "Qty", "Price"]
    - ["Apple", "2",   "$1.00"]
    - ["Bread", "1",   "$3.50"]
  style: single
  header: true
  column_aligns: ["left", "right", "right"]
  output_path: /tmp/preview.txt
response_variable: preview
```

The file (`/tmp/preview.txt`) contains exactly what would print:

```text
┌────────────────┬──────┬───────┐
│Item            │ Qty  │ Price │
├────────────────┼──────┼───────┤
│Apple           │   2  │ $1.00 │
│Bread           │   1  │ $3.50 │
└────────────────┴──────┴───────┘
```

The returned `response_variable` looks like
`{path, width, line_count, codepage}` — useful for chaining a
`notify.<service>` with the rendered output.

**Workflow:** tweak `column_widths` until the preview reads right,
then change `preview_table` → `print_table` (same field set, drop
`output_path`).

## Combining services

Each service is independent — call them back-to-back from an
automation to compose a complete receipt. The printer's lock
serialises the calls so they don't interleave.

```yaml
- action: escpos_printer.print_text_image
  data:
    text: HOME ASSISTANT
    font: dejavu_serif
    font_size: 36
    align: center
    feed: 1

- action: escpos_printer.print_box
  data:
    text: "Daily Report — {{ now().strftime('%Y-%m-%d') }}"
    style: double
    align: center
    padding: 1

- action: escpos_printer.print_table
  data:
    rows:
      - ["Sensor",            "Status"]
      - ["Front door",        "Closed"]
      - ["Garage",            "Closed"]
      - ["Living room temp",  "21.4°C"]
    style: single
    header: true
    column_aligns: ["left", "right"]

- action: escpos_printer.print_separator
  data:
    char: "="
    repeat: 2

- action: escpos_printer.print_kvtable
  data:
    items:
      - ["Open issues",  "{{ states('sensor.todo_count') }}"]
      - ["Power usage",  "{{ states('sensor.daily_kwh') }} kWh"]

- action: escpos_printer.cut
  data:
    mode: full
```

See the [Blueprints directory](../blueprints/README.md) for
ready-to-import automations and scripts that use these patterns.

## Notes & limitations

- **Codepage matters for `print_box` / `print_table`.** The drawing
  glyphs are sent as ordinary text. On a non-cp437-family codepage
  (CP1252, ISO-8859-x, CJK), the existing UTF-8 transcoder swaps the
  Unicode `┌─┐` for ASCII `+-+`; column widths stay correct but the
  visual is no longer "single-line".
- **Cell width assumes 1 char = 1 column.** This is true for the
  cp437-family receipt printers this integration targets. If your
  printer treats certain glyphs (e.g. CJK) as double-width, the
  table column alignment will visually drift even though the
  underlying string is correct.
- **`print_text_image` is slower than text mode.** The bitmap path
  goes through dither + slice + chunked send. For a half-receipt of
  text this is usually a few hundred milliseconds — fine for
  automations, noticeable in tight loops.
- **`rotation` only affects `print_text_image`.** Text-mode services
  (`print_text`, `print_text_utf8`, `print_box`, `print_table`) print
  in the printer's native orientation. To rotate a table or box,
  render it through `print_text_image` instead — pass the laid-out
  table string as `text` to that service.
- **No native ESC/POS rotation.** Some printers expose `ESC V` for
  90° text rotation, but the `python-escpos` version this integration
  pins (`python-escpos==3.1`, see `pyproject.toml`) doesn't expose it;
  the image-render path is the portable substitute. If a future
  python-escpos release adds the bind, this note is the canary to
  re-evaluate the text path.

## CJK / wide-character content {#cjk}

Text-mode services (`print_box`, `print_table`, `print_kvtable`)
measure cell width in Python characters — they treat every codepoint
as one column. That assumption holds for Latin/Cyrillic/Greek/cp437
content, but breaks for **CJK ideographs, fullwidth punctuation, and
most emoji**, which render two terminal columns wide. The result is
silently misaligned columns: the data is correct but the visual
gridlines drift.

The **first time** `print_box`, `print_table`, or `print_kvtable`
sees wide-width characters in the input it logs a one-shot warning:

```text
Box content contains wide-width characters (CJK / fullwidth /
emoji); the borders may misalign because textwrap wraps by
code-point count, not display columns. Use print_text_image for
accurate layout — see docs/text-effects.md#cjk.
(This warning fires once per process.)
```

The warning is **hint-only** — the renderer still produces output
even when wide glyphs are present, just without per-glyph column
awareness. Detection samples the first 256 characters of each
input; if the only wide glyphs appear later in a long string the
warning may not fire, but the renderer's output is identical either
way (the data is correct; only visual alignment differs).

**The recommended workaround** is to render the layout through
`print_text_image` instead: the image renderer measures actual glyph
advances (including CJK and emoji), so the columns line up visually
even if the underlying string mixes scripts. Pick `dejavu_sans` or
supply a CJK-capable font via `font_path` (e.g. Noto Sans CJK).
