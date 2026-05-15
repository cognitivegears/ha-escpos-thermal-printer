# USB Printers

For directly-attached USB thermal printers.

## Requirements

- libusb library on the Home Assistant host (preinstalled on HA OS)
- Printer connected via USB
- USB permissions (udev rules on Linux for non-HA-OS installs)

## Auto-discovery

USB printers from known thermal-printer vendors are auto-discovered when plugged in. HA shows a notification prompting configuration.

Recognized vendor IDs include Epson (0x04B8), Star Micronics (0x0519), Citizen (0x08BD/0x1D90/0x2730), Bixolon (0x1504), Zebra (0x0A5F), and ~15 others. The full list is in `custom_components/escpos_printer/manifest.json` under the `usb:` key.

## Manual configuration

If your printer isn't auto-discovered:

1. Choose **USB** as connection type
2. Select **Browse all USB devices** or **Manual entry**
3. For manual entry, provide:
   - **Vendor ID** — from `lsusb` (Linux) or Device Manager (Windows)
   - **Product ID** — listed alongside Vendor ID
   - **Endpoints** — usually `0x82` (in) and `0x01` (out)

## Connection settings

| Setting | Description | Default |
|---------|-------------|---------|
| Vendor ID | USB Vendor ID (hex, e.g. 04B8) | From discovery |
| Product ID | USB Product ID (hex, e.g. 0E03) | From discovery |
| Input Endpoint | USB IN endpoint | 0x82 |
| Output Endpoint | USB OUT endpoint | 0x01 |
| Timeout | Connect timeout (seconds) | 4.0 |
| Printer Profile | Your printer model | Auto-detect |

## USB permissions on Linux

If you see `Permission denied`, create a udev rule:

```bash
# /etc/udev/rules.d/99-escpos.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", MODE="0666"
```

Replace `04b8` with your printer's vendor ID. Reload:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

## Docker container deployments

USB needs device pass-through:

```yaml
services:
  homeassistant:
    devices:
      - /dev/bus/usb:/dev/bus/usb
```

Or pass-through a specific device (e.g. `/dev/usb/lp0`).

## Common issues

- **"Permission denied"** — add a udev rule (above) or run on HA OS.
- **"Device not found"** — verify with `lsusb`; check cable; try another USB port.
- **"Input/Output Error" / errno 5** — usually USB autosuspend or another driver holding the device. Disable autosuspend or replug.
- **Wrong endpoints** — defaults are 0x82/0x01; if those fail, find correct ones with `lsusb -v -d VENDOR:PRODUCT | grep Endpoint`.

See [troubleshooting.md](troubleshooting.md#usb-issues) for more.
