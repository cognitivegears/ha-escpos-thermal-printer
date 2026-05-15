# ESC/POS Thermal Printer for Home Assistant

Native Home Assistant control for ESC/POS thermal receipt printers connected via **Network (TCP/IP)**, **USB**, or **Bluetooth**.

- **Print services** — text (raw + UTF-8 transcoding), QR codes, barcodes, images, and free-form messages
- **Control services** — paper feed, partial/full cut, beeper
- **Notification platform** — pipe HA notifications straight to a printer
- **Status binary sensor** — reachability check works for network, USB, and Bluetooth
- **Battery sensor** — reports battery level for portable BT printers that expose `org.bluez.Battery1`
- **Auto-discovery** — USB printers matched against known thermal-printer vendor IDs
- **Local push** — no cloud, no account

## Setup

After install, restart Home Assistant and add the integration from **Settings → Devices & Services**. Pick your connection type (Network, USB, or Bluetooth) and follow the prompts.

**Bluetooth users**: pair the printer on the host (e.g. via `bluetoothctl pair AA:BB:CC:DD:EE:FF`) **before** adding the integration. The integration does not initiate pairing itself.

## Documentation

See the [README](https://github.com/cognitivegears/ha-escpos-thermal-printer#readme) and the [docs/](https://github.com/cognitivegears/ha-escpos-thermal-printer/tree/main/docs) folder for the full configuration reference, automation examples, troubleshooting, and known limitations.
