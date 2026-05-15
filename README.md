# ESC/POS Thermal Printer for Home Assistant

[![Validate](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml)
[![Hassfest](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml)

Print receipts, labels, QR codes, and more from Home Assistant automations.
Connect any ESC/POS capable network, USB, or bluetooth thermal printer and
start printing in minutes.

![Printed Receipt Example](docs/assets/receipt.png)

## Why Use This?

- **Automate physical output** - Print door access logs, temperature alerts,
todo lists, daily reports, or shopping lists automatically
- **Works with cheap hardware** - Any $30+ thermal printer (network, USB, or bluetooth)
that supports ESC/POS will work
- **Network, USB, and bluetooth support** - Connect via TCP/IP, plug directly via
USB, or print wirelessly
- **Multiple printers** - Set up as many printers as you need and target them
individually or broadcast to all
- **No cloud required** - Direct connection to your printers, everything stays local

## Features

- Print text with formatting (bold, underline, alignment, font sizes)
- Print QR codes, barcodes, and images
- Paper feed and cut control
- Buzzer/beeper support
- UTF-8 text with automatic character conversion
- 35+ printer profiles with automatic feature detection
- Full UI configuration, no YAML required

## Quick Start

### Requirements

- **Home Assistant 2026.2 or later** (older HA versions don't ship the
  `dbus-fast` 4.x APIs the Bluetooth flow needs; 0.4.x of this
  integration still works on HA 2024.8+ if you're stuck there)
- Thermal printer with ESC/POS support (most receipt printers)
- **Network printers:** Accessible on your network (typically port 9100)
- **USB printers:** Connected directly to your Home Assistant host (requires libusb)
- **Bluetooth printers:** Linux host with kernel `AF_BLUETOOTH` support;
  printer paired on the host before adding to HA. See [Bluetooth printers](docs/bluetooth.md).

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

## Available Services

| Service | Description |
|---------|-------------|
| `escpos_printer.print_text` | Print formatted text in the device encoding |
| `escpos_printer.print_text_utf8` | Print UTF-8 text with automatic character conversion |
| `escpos_printer.print_message` | Print formatted message via notify entity (supports all text formatting + UTF-8) |
| `escpos_printer.print_qr` | Print QR codes |
| `escpos_printer.print_barcode` | Print barcodes (EAN13, CODE128, etc.) |
| `escpos_printer.print_image` | Print images from URL or local path |
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

## Documentation

| Document | Description |
|----------|-------------|
| [Installation](docs/installation.md) | HACS / manual install, removal |
| [Configuration](docs/configuration.md) | Common settings reference (codepage, line width, defaults) |
| [Network printers](docs/network.md) | TCP/IP setup |
| [USB printers](docs/usb.md) | USB setup, permissions, container pass-through |
| [Bluetooth printers](docs/bluetooth.md) | Pairing, RFCOMM, container caveats |
| [Services](docs/services.md) | Service parameter reference |
| [Automations](docs/automations.md) | Automation examples |
| [Notifications](docs/notifications.md) | Notify entity and `print_message` service |
| [Multi-printer targeting](docs/multi-printer.md) | `target:` blocks, area / entity / device targeting |
| [Limitations](docs/limitations.md) | Known limitations |
| [Troubleshooting](docs/troubleshooting.md) | Common issues and solutions |
| [Contributing](CONTRIBUTING.md) | Contributing, testing, and local development |

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/cognitivegears/ha-escpos-thermal-printer/discussions)

## License

MIT License - see [LICENSE](LICENSE) for details.
