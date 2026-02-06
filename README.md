# ESC/POS Thermal Printer for Home Assistant

[![Validate](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml)
[![Hassfest](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml)
[![HACS Validation](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml/badge.svg)](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml)

Print receipts, labels, QR codes, and more from Home Assistant automations.
Connect thermal printers via CUPS and start printing in minutes.

![Printed Receipt Example](docs/assets/receipt.png)

## Why Use This?

- **Automate physical output** – Print door access logs, temperature alerts, todo lists, daily reports, or shopping lists automatically
- **Works with cheap hardware** – Any thermal printer that supports ESC/POS commands will work
- **USB and Network printers** – Use CUPS to connect USB printers or network printers
- **Remote CUPS servers** – Print to printers connected to another machine on your network
- **Multiple printers** – Set up as many printers as you need and target them individually or broadcast to all
- **No cloud required** – Everything stays local on your network

## Features

- Print text with formatting (bold, underline, alignment, font sizes)
- Print QR codes, barcodes, and images
- Paper feed and cut control
- Buzzer/beeper support
- UTF-8 text with automatic character conversion
- 35+ printer profiles with automatic feature detection
- Full UI configuration – no YAML required

## How It Works

This integration uses **CUPS** (Common Unix Printing System) to send ESC/POS commands to your thermal printer:

1. Connects to a CUPS server (local or remote) via the `pycups` library
2. Builds ESC/POS commands using `python-escpos`'s Dummy printer
3. Submits raw print jobs directly to your CUPS printer queue

This approach allows printing to both USB-connected and network printers, as long as they're configured in CUPS.

```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│ Home Assistant  │──▶│  CUPS Server    │──▶│ Thermal Printer │
│ (this integration)│  │ (local/remote)  │   │ (USB/Network)   │
└─────────────────┘   └─────────────────┘   └─────────────────┘
        │                      │
        │ pycups library       │ Raw ESC/POS
        │ (IPP protocol)       │ commands
        ▼                      ▼
   Builds ESC/POS         Forwards to
   commands using         printer unchanged
   python-escpos
```

## Quick Start

### Requirements

- Home Assistant 2024.8 or later
- A **CUPS server** with your thermal printer configured
  - Can be on the same machine as Home Assistant
  - Can be a remote CUPS server on your network (e.g., a Raspberry Pi, NAS, or dedicated print server)
- Thermal printer with ESC/POS support configured in CUPS as a **raw** queue

### Setting Up CUPS

If you don't have CUPS configured yet:

1. **Install CUPS** on your print server:
   ```bash
   # Debian/Ubuntu/Raspberry Pi OS
   sudo apt install cups
   
   # Enable remote access (if Home Assistant is on a different machine)
   sudo cupsctl --remote-any
   sudo systemctl restart cups
   ```

2. **Add your printer** via the CUPS web interface at `http://your-server:631`:
   - For USB printers: CUPS will auto-detect them under "Local Printers"
   - For network printers: Add as AppSocket/HP JetDirect with address `socket://printer-ip:9100`
   - **Configure as raw queue**: When adding the printer, select "Raw" as the Make/Driver so CUPS passes ESC/POS commands through unchanged. This is critical – using a specific printer driver will corrupt the ESC/POS data.

3. **Test the printer**:
   ```bash
   # Print a test message
   echo "Hello from CUPS" | lp -d YourPrinterName
   ```

### Install via HACS

1. Open HACS in Home Assistant
2. Go to Integrations and click the menu (three dots)
3. Select **Custom repositories**
4. Add `https://github.com/cognitivegears/ha-escpos-thermal-printer` as an Integration
5. Search for "ESC/POS Thermal Printer" and install it
6. Restart Home Assistant

### Configure Your Printer

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for "ESC/POS Thermal Printer"
3. Enter your CUPS server address (leave empty for localhost)
4. Select your printer from the list of available CUPS printers
5. Choose your printer profile or use "Auto-detect"
6. Configure optional settings (character encoding, line width, etc.)
7. Done! Your printer is ready to use

## Basic Examples

### Print a Message

```yaml
service: escpos_printer.print_text
data:
  text: "Hello from Home Assistant!"
  align: center
  cut: partial
```

### Print with Formatting

```yaml
service: escpos_printer.print_text
data:
  text: "IMPORTANT ALERT"
  align: center
  bold: true
  width: double
  height: double
  underline: single
  cut: partial
  feed: 2
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

### Print a Barcode

```yaml
service: escpos_printer.print_barcode
data:
  code: "4006381333931"
  bc: EAN13
  height: 80
  width: 3
  pos: BELOW
  align: center
  cut: partial
```

### Print an Image

```yaml
service: escpos_printer.print_image
data:
  image: "https://example.com/logo.png"
  align: center
  cut: partial
```

You can also print local images:

```yaml
service: escpos_printer.print_image
data:
  image: "/config/www/images/logo.png"
  align: center
  cut: partial
```

### Target a Specific Printer

When you have multiple printers, use `target` to select which one:

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
| `escpos_printer.print_text` | Print formatted text using device encoding |
| `escpos_printer.print_text_utf8` | Print UTF-8 text with automatic character conversion |
| `escpos_printer.print_qr` | Print QR codes |
| `escpos_printer.print_barcode` | Print barcodes (EAN13, EAN8, CODE128, CODE39, UPC-A, etc.) |
| `escpos_printer.print_image` | Print images from URL or local path |
| `escpos_printer.feed` | Feed paper by number of lines |
| `escpos_printer.cut` | Cut paper (full or partial) |
| `escpos_printer.beep` | Sound the buzzer (if supported by printer) |

## Service Parameters

### print_text / print_text_utf8

| Parameter | Description | Default |
|-----------|-------------|---------|
| `text` | Text content to print (required) | – |
| `align` | Alignment: `left`, `center`, `right` | `left` |
| `bold` | Bold text | `false` |
| `underline` | Underline: `none`, `single`, `double` | `none` |
| `width` | Width: `normal`, `double`, `triple` | `normal` |
| `height` | Height: `normal`, `double`, `triple` | `normal` |
| `cut` | Cut mode: `none`, `partial`, `full` | `partial` |
| `feed` | Lines to feed after printing | `0` |

### print_qr

| Parameter | Description | Default |
|-----------|-------------|---------|
| `data` | Data to encode in QR code (required) | – |
| `size` | Module size (1-16) | `3` |
| `ec` | Error correction: `L`, `M`, `Q`, `H` | `M` |
| `align` | Alignment: `left`, `center`, `right` | `left` |
| `cut` | Cut mode after printing | `partial` |
| `feed` | Lines to feed after printing | `0` |

### print_barcode

| Parameter | Description | Default |
|-----------|-------------|---------|
| `code` | Barcode data (required) | – |
| `bc` | Barcode type (required): `EAN13`, `EAN8`, `CODE128`, `CODE39`, `UPC-A`, etc. | – |
| `height` | Barcode height in dots (1-255) | `64` |
| `width` | Module width (2-6) | `3` |
| `pos` | Text position: `ABOVE`, `BELOW`, `BOTH`, `OFF` | `BELOW` |
| `align` | Alignment: `left`, `center`, `right` | `left` |
| `cut` | Cut mode after printing | `partial` |
| `feed` | Lines to feed after printing | `0` |

### print_image

| Parameter | Description | Default |
|-----------|-------------|---------|
| `image` | URL or local path to image (required) | – |
| `high_density` | Use high density printing mode | `true` |
| `align` | Alignment: `left`, `center`, `right` | `left` |
| `cut` | Cut mode after printing | `partial` |
| `feed` | Lines to feed after printing | `0` |

## Supported Printers

This integration works with any ESC/POS thermal printer configured in CUPS, including:

- Epson TM series (TM-T20, TM-T88, TM-U220, TM-M30, etc.)
- Star Micronics (TSP100, TSP650, TSP700, mPOP, etc.)
- Citizen (CT-S2000, CT-S310, CT-S601, etc.)
- Bixolon (SRP-350, SRP-380, etc.)
- POS-X and other generic 58mm/80mm thermal receipt printers

Printers can be connected via:

- **USB** – Connected directly to your CUPS server
- **Network** – Configured in CUPS as AppSocket/JetDirect (`socket://ip:9100`)
- **Serial** – With appropriate CUPS backend configuration

## Automation Examples

### Print Daily Weather Summary

```yaml
automation:
  - alias: "Print Morning Weather"
    trigger:
      - platform: time
        at: "07:00:00"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            ═══════════════════════════
                 WEATHER TODAY
            ═══════════════════════════
            
            {{ states('sensor.temperature') }}°F
            {{ states('sensor.weather_condition') }}
            
            High: {{ states('sensor.forecast_high') }}°F
            Low: {{ states('sensor.forecast_low') }}°F
            
            {{ now().strftime('%A, %B %d, %Y') }}
          align: center
          cut: partial
```

### Print Doorbell Alert

```yaml
automation:
  - alias: "Print Doorbell Ring"
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell
        to: "on"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            *** DOORBELL ***
            
            Someone is at the door!
            
            Time: {{ now().strftime('%I:%M %p') }}
          align: center
          bold: true
          cut: partial
```

### Print Shopping List

```yaml
script:
  print_shopping_list:
    sequence:
      - service: escpos_printer.print_text
        data:
          text: |
            ═══════════════════════════
                 SHOPPING LIST
            ═══════════════════════════
            {% for item in states.sensor.shopping_list.attributes.items %}
            [ ] {{ item }}
            {% endfor %}
            
            {{ now().strftime('%Y-%m-%d %H:%M') }}
          cut: partial
```

## Troubleshooting

### No printers found during setup

- Verify the CUPS server address is correct
- Check that the CUPS server allows remote connections: `sudo cupsctl --remote-any`
- Ensure the printer appears in the CUPS web interface at `http://server:631/printers`
- Check firewall allows port 631 (IPP)

### Jobs submitted but nothing prints

- Check the CUPS job queue: `lpstat -o` or via web interface
- Verify the printer is not paused in CUPS
- **Important**: Ensure the printer is configured as a "Raw" queue – using a specific driver will corrupt ESC/POS commands
- Check printer is online and has paper

### Garbled or corrupted output

- The printer driver in CUPS must be set to "Raw"
- Check that the correct printer profile is selected in the integration
- Try "Auto-detect" profile or select your specific printer model

### Connection refused to remote CUPS

- Enable remote access: `sudo cupsctl --remote-any`
- Check firewall allows port 631
- Verify CUPS is running: `sudo systemctl status cups`
- Check the CUPS server address in integration config (hostname or IP, no `http://`)

### Integration won't load after removing and re-adding

- This was a known issue with stale CUPS connection state – update to the latest version
- Restart Home Assistant after removing the integration before re-adding

## Documentation

| Document | Description |
|----------|-------------|
| Configuration Guide | Detailed setup options, printer profiles, and settings |
| Examples | Complete examples for receipts, automations, and multi-printer setups |
| Troubleshooting | Common issues and solutions |
| Contributing | Contributing, testing, and local development |

## Getting Help

- **Issues**: [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/cognitivegears/ha-escpos-thermal-printer/discussions)

## License

MIT License – see [LICENSE](LICENSE) for details.
