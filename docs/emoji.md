# Emoji

ESC/POS printers know a few hundred characters per codepage and no emoji at all, so a `😀` normally comes out as `?`. The integration draws emoji itself instead.

## How it works

Lines that contain an emoji are rendered to a small black-and-white bitmap with the bundled monochrome *Noto Emoji* font and printed as an image. Every other line is still sent as fast, native text. Both go over one connection, so the receipt prints in order.

```yaml
action: escpos_printer.print_text_utf8
data:
  text: |
    Garage
    🚪 Door is open
    Close it before you leave 👋
  align: center
  cut: partial
```

Alignment, font (A or B) and the size multipliers (`width` / `height`) apply to emoji lines as well. Bold, underline and invert do not, because the line is a picture.

## The `emoji` option

`print_text_utf8` takes an `emoji` option:

| Value | Behavior |
|-------|----------|
| `auto` (default) | Emoji lines are printed as images. Text without emoji is not affected at all. |
| `strip` | Emoji are removed, together with the space they leave behind. |
| `off` | Emoji print as `?`, like in earlier versions. |

The notify entity's `print_message` action takes the same `emoji` option. It applies whenever `utf8: true` is set and no image is attached.

Emoji lines are rendered before anything is sent to the printer. A long run of emoji lines is split into several images, so it prints at any size; if a line can't be rendered at all, the call fails with nothing printed.

## Which emoji work

Anything the bundled font covers, roughly 1,400 symbols: faces, people, animals, food, travel, objects, symbols and flags. Sequences are understood:

| Sequence | Printed as |
|----------|-----------|
| Skin tones (`👍🏽`) | the neutral `👍` |
| Joined emoji (`👩‍💻`) | the parts side by side, `👩💻` |
| Flags (`🇩🇪`) | the two regional-indicator letters in a box |
| Keycaps (`1️⃣`) | the digit in a keycap |
| Text symbols with the emoji selector (`❤️`) | the emoji form |

The font is monochrome, so colors are gone: the printer only prints black anyway. Symbols such as `♥`, `©` or `✓` stay plain text unless they carry the emoji selector (`♥️`).

## `print_text_image`

The [`print_text_image`](text-effects.md) service draws emoji the same way. Pick any font for the text; emoji fall back to the bundled one automatically.

## Credits

The emoji font is [Noto Emoji](https://github.com/google/fonts/tree/main/ofl/notoemoji) by Google, licensed under the SIL Open Font License 1.1. See [NOTICE](../NOTICE).
