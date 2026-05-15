# Installation

## Via HACS (recommended)

1. **HACS** → **Integrations** → **⋮** → **Custom repositories**
2. Add `https://github.com/cognitivegears/ha-escpos-thermal-printer` as an Integration
3. Install **ESC/POS Thermal Printer** and restart Home Assistant
4. **Settings** → **Devices & services** → **Add Integration** → search "ESC/POS Thermal Printer"

## Manual install

1. Copy `custom_components/escpos_printer/` into your Home Assistant config directory's `custom_components/` folder
2. Restart Home Assistant
3. Add the integration from **Settings → Devices & services**

## Adding your first printer

After install, **Settings** → **Devices & services** → **Add Integration** → **ESC/POS Thermal Printer**. Pick your connection type:

- **Network (TCP/IP)** — for printers with Ethernet/WiFi
- **USB** — for direct-attached printers (auto-discovery for known vendor IDs)
- **Bluetooth (RFCOMM)** — for portable battery-powered printers; **pair on the host first**

Then follow the connection-specific guide:

- [Network setup](network.md)
- [USB setup](usb.md)
- [Bluetooth setup](bluetooth.md)

After the connection step, you'll be asked for common settings (codepage, line width, default alignment, default cut). See [configuration.md](configuration.md).

## Removing the integration

1. **Settings** → **Devices & services** → click **ESC/POS Thermal Printer**
2. Click the **⋮** menu on the entry → **Delete**
3. (Optional) remove `custom_components/escpos_printer/` from your config directory if you want to remove the code as well.

Removing an entry tears down the adapter, unloads the binary sensor / notify entity / battery sensor, and removes the device from the registry.
