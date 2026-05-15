# Configuration Reference

Settings that apply to all connection types. For connection-specific options, see [network.md](network.md), [usb.md](usb.md), or [bluetooth.md](bluetooth.md).

After initial setup, click **Configure** on the integration entry to change these.

## Printer Profile

Selects your printer model from the bundled [escpos-printer-db](https://github.com/receipt-print-hq/escpos-printer-db) (~35 profiles). The profile determines available codepages, line width options, supported cut modes, and other capabilities.

- **Auto-detect** — works with most printers; use if your model isn't listed.
- **Custom** — type a profile name from escpos-printer-db manually.

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

## Default Alignment

Applied when a service call doesn't specify `align`: `left` (default), `center`, `right`.

## Default Cut Mode

Applied when a service call doesn't specify `cut`: `none` (default), `partial`, `full`.

## Keep Alive (network only)

Maintains a persistent TCP connection. Reduces print latency at the cost of misbehaving when the printer goes offline. **Network only.** USB and Bluetooth always reconnect per operation.

## Status Interval

How often to probe the printer (seconds). Set to 0 to disable. Drives the binary sensor.

- **Network**: any value works; default 30s is fine.
- **Bluetooth**: set to 60s or longer (or 0). RFCOMM accepts only one client at a time, and many cheap BT printers beep on every connect. The integration auto-skips probes during prints, so aggressive polling has no benefit.
