# ESC/POS Thermal Printer for Home Assistant

[![Validate](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml)
[![Hassfest](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml)

Print receipts, labels, QR codes, and more from Home Assistant automations.
Connect any network or USB thermal printer and start printing in minutes.

![Printed Receipt Example](docs/assets/receipt.png)

## Why Use This?

- **Automate physical output** - Print door access logs, temperature alerts,
todo lists, daily reports, or shopping lists automatically
- **Works with cheap hardware** - Any $30+ thermal printer (network or USB) that supports
ESC/POS will work
- **Network and USB support** - Connect via TCP/IP or plug directly via USB
- **Multiple printers** - Set up as many printers as you need and target them individually or broadcast to all
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

- Home Assistant 2024.8 or later
- Thermal printer with ESC/POS support (most receipt printers)
- **Network printers:** Accessible on your network (typically port 9100)
- **USB printers:** Connected directly to your Home Assistant host (requires libusb)

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

**Note:** USB printers may be auto-discovered when connected. Check your Home Assistant notifications.

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

## Documentation

| Document | Description |
|----------|-------------|
| [Configuration Guide](docs/CONFIGURATION.md) | Detailed setup options, printer profiles, and settings |
| [Examples](docs/EXAMPLES.md) | Complete examples for receipts, automations, and multi-printer setups |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common issues and solutions |
| [Contributing](CONTRIBUTING.md) | Contributing, testing, and local development |

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/cognitivegears/ha-escpos-thermal-printer/discussions)

## License

MIT License - see [LICENSE](LICENSE) for details.
