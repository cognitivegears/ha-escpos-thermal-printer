# ESC/POS Thermal Printer for Home Assistant

[![Validate](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml)
[![Hassfest](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml)

Print receipts, labels, QR codes, and more from Home Assistant automations.
Connect any ESC/POS capable network, USB, bluetooth, or serial thermal printer and
start printing in minutes.

![Printed Receipt Example](docs/assets/receipt.png)

## Why Use This?

- **Automate physical output** - Print door access logs, temperature alerts,
todo lists, daily reports, or shopping lists automatically

- **Works with cheap hardware** - Any $30+ thermal printer (network, USB, bluetooth,
or serial) that supports ESC/POS will work

- **Network, USB, Bluetooth, and serial support** - Connect via TCP/IP, plug directly
via USB, print wirelessly over Bluetooth, or use a serial (UART/RS-232) or ESPHome
serial proxy connection

- **Multiple printers** - Set up as many printers as you need and target them
individually or broadcast to all

- **No cloud required** - Direct connection to your printers, everything stays local

## Features

- Print text with formatting (bold, underline, alignment, font sizes)
- Print QR codes, barcodes, and images — from URLs, files, camera/image entities, or base64 ([guide](docs/images.md))
- Text effects — boxes, multi-column tables, and custom-font / rotated text ([guide](docs/text-effects.md))
- Paper feed and cut control
- Buzzer/beeper support
- UTF-8 text with automatic character conversion
- 35+ printer profiles with automatic feature detection
- Full UI configuration, no YAML required

## Quick Start

### Requirements

- **Home Assistant 2026.5 or later** (serial support needs the
  `SerialPortSelector` introduced in HA 2026.5, and the integration
  tracks HA core's bundled Pillow / dbus-fast pins; 0.4.x of this
  integration still works on HA 2024.8+ if you're stuck there)
- Thermal printer with ESC/POS support (most receipt printers)
- **Network printers:** Accessible on your network (typically port 9100)
- **USB printers:** Connected directly to your Home Assistant host (requires libusb)
- **Bluetooth printers:** Linux host with kernel `AF_BLUETOOTH` support;
  printer paired on the host before adding to HA. See [Bluetooth printers](docs/bluetooth.md).
- **Serial printers:** Linux host with serial port access (`dialout` group); or use
  an ESPHome serial proxy over the network. See [Serial printers](docs/serial.md).

### Install via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations** and click the menu (three dots)
3. Select **Custom repositories**
4. Add `https://github.com/cognitivegears/ha-escpos-thermal-printer` as an Integration
5. Search for "ESC/POS Thermal Printer" and install it
6. Restart Home Assistant

### Configure Your Printer

1. Go to **Settings** > **Devices & services** > **Add Integration**
2. Search for "ESC/POS Thermal Printer"
3. Select your connection type:
   - **Network:** Enter your printer's IP address and port (default: 9100)
   - **USB:** Select from auto-discovered printers or enter VID:PID manually
4. Select your printer model or use "Auto-detect"
5. Done! Your printer is ready to use

**Note:** USB printers may be auto-discovered when connected. Check your Home
Assistant notifications.

## Basic Examples

### Print a Message

```yaml
service: escpos_printer.print_text
data:
  text: "Hello from Home Assistant!"
  align: center
  cut: partial
```

### Print a QR Code

```yaml
service: escpos_printer.print_qr
data:
  data: "https://www.home-assistant.io"
  size: 8
  align: center
  cut: partial
```

### Target a Specific Printer

When you have multiple printers, use `target` to pick which one:

```yaml
service: escpos_printer.print_text
target:
  device_id: your_printer_device_id
data:
  text: "Sent to a specific printer"
  cut: partial
```

Omit `target` to broadcast to all configured printers.

### Print a Bordered Header

```yaml
service: escpos_printer.print_box
data:
  text: DAILY REPORT
  style: auto         # → single-line ┌─┐ on CP437; ASCII otherwise
  padding: 1
  align: center
  feed: 1
```

### Print a Receipt-Style Table

```yaml
service: escpos_printer.print_table
data:
  rows:
    - ["Item", "Qty", "Price"]
    - ["Coffee", "2", "$6.00"]
    - ["Bagel",  "1", "$3.50"]
  style: single
  header: true
  column_aligns: ["left", "center", "right"]
```

### Print Receipt Totals (Label/Value Pairs)

```yaml
service: escpos_printer.print_kvtable
data:
  items:
    - ["Subtotal", "$10.00"]
    - ["Tax",      "$0.80"]
    - ["Total",    "$10.80"]
```

See the [Text effects guide](docs/text-effects.md) for the full
reference (boxes, tables, kv-tables, separators, custom-font /
rotated text via `print_text_image`, and the previewing workflow).
For ready-to-import scripts and automations see the
[Blueprints directory](blueprints/README.md).

## Available Services

| Service | Description |
|---------|-------------|
| `escpos_printer.print_text` | Print formatted text in the device encoding |
| `escpos_printer.print_text_utf8` | Print UTF-8 text with automatic character conversion |
| `escpos_printer.print_message` | Print formatted message via notify entity (supports all text formatting + UTF-8) |
| `escpos_printer.print_qr` | Print QR codes |
| `escpos_printer.print_barcode` | Print barcodes (EAN13, CODE128, etc.) |
| `escpos_printer.print_image` | Print images from URL, file, camera/image entity, or base64 — see [Images guide](docs/images.md) |
| `escpos_printer.print_image_url` | Focused convenience service for HTTP(S) URLs (UI gets a URL field) — see [Images guide](docs/images.md) |
| `escpos_printer.print_image_path` | Focused convenience service for local file paths — see [Images guide](docs/images.md) |
| `escpos_printer.print_camera_snapshot` | Print a live snapshot from a `camera.<id>` entity (UI gets an entity picker) |
| `escpos_printer.print_image_entity` | Print the current frame from an `image.<id>` entity |
| `escpos_printer.print_box` | Wrap text in a printable border (cp437 / ASCII / asterisk / hash) — see [Text effects guide](docs/text-effects.md) |
| `escpos_printer.print_table` | Print multi-column rows (receipts, logs) — see [Text effects guide](docs/text-effects.md) |
| `escpos_printer.print_kvtable` | Print two-column label/value pairs (receipt totals, sensor readings) — see [Text effects guide](docs/text-effects.md) |
| `escpos_printer.print_separator` | Print a single decorative rule (line of repeated characters) |
| `escpos_printer.print_text_image` | Render text with a TTF/OTF font and optional 90/180/270° rotation — see [Text effects guide](docs/text-effects.md) |
| `escpos_printer.preview_image` | Run the image pipeline and write the resulting 1-bit PNG to disk (no paper) — see [Images guide](docs/images.md) |
| `escpos_printer.preview_box` | Render a `print_box` layout to a `.txt` file (no paper) |
| `escpos_printer.preview_table` | Render a `print_table` layout to a `.txt` file (no paper) |
| `escpos_printer.calibration_print` | Print a ruler + threshold sweep strip so you can pick dither/threshold without burning a roll |
| `escpos_printer.feed` | Feed paper |
| `escpos_printer.cut` | Cut paper |
| `escpos_printer.beep` | Sound the buzzer |

## Supported Printers

This integration works with any printer supported by
[python-escpos](https://python-escpos.readthedocs.io/), including:

- Epson TM series (TM-T20, TM-T88, TM-U220, etc.)
- Star Micronics (TSP100, TSP650, TSP700, etc.)
- Citizen (CT-S2000, CT-S310, CT-S601, etc.)
- Most generic 58mm and 80mm thermal receipt printers

## Bluetooth (RFCOMM) printers

Cheap thermal printers (Netum, MUNBYN, POS-58 generics, Phomemo Classic line, etc.) connect over **Bluetooth Classic / RFCOMM**. Pair the printer on the host first, then add it in HA — the integration opens a raw RFCOMM socket to an already-paired device but does not handle pairing itself. Bluetooth Classic is plaintext by default, so don't route sensitive content (OTPs, 2FA codes, door logs) to a BT printer.

See [docs/bluetooth.md](docs/bluetooth.md) for the full pairing walkthrough, container deployment notes, the `socat` host-bridge fallback, and security considerations.

## Serial (UART/RS-232) printers

For printers connected via a physical serial cable or a network-based serial proxy. Supports direct device paths (`/dev/ttyUSB0`), ESPHome UART proxies (`esphome://host:port`), RFC2217 serial servers, and raw TCP sockets. On Linux, the HA user needs to be in the `dialout` group.

See [docs/serial.md](docs/serial.md) for setup instructions, ESPHome YAML examples, write-chunking options for ESP32 buffer overruns, and troubleshooting.

## Blueprints

The [`blueprints/`](blueprints/) directory ships 13 ready-to-import Home Assistant scripts and automations that exercise the text-effects services. They cover the common day-to-day workflows so you don't need to write YAML from scratch.

| Blueprint | Type | Use case |
|-----------|------|----------|
| [Shopping List](blueprints/script/escpos_printer/shopping_list.yaml) | Script | Print a `todo` entity as a bordered grocery list. |
| [TODO List](blueprints/script/escpos_printer/todo_list.yaml) | Script | Generic todo printer — any list, optional completed items, optional numbering. |
| [Daily Agenda](blueprints/automation/escpos_printer/daily_agenda.yaml) | Automation | Print today's calendar events at a fixed time each day. |
| [Weather Forecast](blueprints/script/escpos_printer/weather_forecast.yaml) | Script | Print an N-day forecast table. |
| [Receipt](blueprints/script/escpos_printer/receipt.yaml) | Script | Itemised receipt with subtotal / tax / total. |
| [Recipe Card](blueprints/script/escpos_printer/recipe_card.yaml) | Script | Kitchen card — name, servings, ingredients, numbered steps. |
| [Guest Wi-Fi QR](blueprints/script/escpos_printer/guest_wifi_qr.yaml) | Script | Print a scannable Wi-Fi join QR code for guests. |
| [Sensor Alert](blueprints/automation/escpos_printer/sensor_alert.yaml) | Automation | Print a bordered alert when a sensor reaches a target state. |
| [TODO Item](blueprints/automation/escpos_printer/todo_item.yaml) | Automation | Print a card per item added to a `todo` entity (fridge-printer style). |
| [TODO Ticket](blueprints/automation/escpos_printer/todo_ticket.yaml) | Automation | Print a ticket (with QR) per item added to a `todo` entity. |
| [Doorbell Snapshot](blueprints/automation/escpos_printer/doorbell_snapshot.yaml) | Automation | Print a camera snapshot when the doorbell is pressed. |
| [Morning Briefing](blueprints/automation/escpos_printer/morning_briefing.yaml) | Automation | Print a combined weather + agenda briefing each morning. |
| [Trash Reminder](blueprints/automation/escpos_printer/trash_reminder.yaml) | Automation | Print a bin / recycling reminder on collection eve. |

See [`blueprints/README.md`](blueprints/README.md) for import instructions, per-blueprint inputs, and troubleshooting notes.

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/installation.md) | HACS / manual install, removal |
| [Configuration](docs/configuration.md) | Common settings reference (codepage, line width, defaults) |
| [Network printers](docs/network.md) | TCP/IP setup |
| [USB printers](docs/usb.md) | USB setup, permissions, container pass-through |
| [Bluetooth printers](docs/bluetooth.md) | Pairing, RFCOMM, container caveats |
| [Serial printers](docs/serial.md) | Serial/UART setup, ESPHome proxy, write chunking |
| [Services](docs/services.md) | Service parameter reference |
| [Images](docs/images.md) | Image printing — sources, processing, reliability, recipes |
| [Text effects](docs/text-effects.md) | Boxes, multi-column tables, and custom-font / rotated text |
| [Automations](docs/automations.md) | Automation examples |
| [Notifications](docs/notifications.md) | Notify entity and `print_message` service |
| [Multi-printer targeting](docs/multi-printer.md) | `target:` blocks, area / entity / device targeting |
| [Limitations](docs/limitations.md) | Known limitations |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [Contributing](CONTRIBUTING.md) | Contributing, testing, and local development |
| [Contributors](CONTRIBUTORS.md) | People who have contributed to this project |

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/cognitivegears/ha-escpos-thermal-printer/discussions)

## License

MIT License - see [LICENSE](LICENSE) for details.
