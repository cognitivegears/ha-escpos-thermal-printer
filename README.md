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

- **Home Assistant 2026.2 or later** (older HA versions don't ship the
  `dbus-fast` 4.x APIs the Bluetooth flow needs; 0.4.x of this
  integration still works on HA 2024.8+ if you're stuck there)
- Thermal printer with ESC/POS support (most receipt printers)
- **Network printers:** Accessible on your network (typically port 9100)
- **USB printers:** Connected directly to your Home Assistant host (requires libusb)
- **Bluetooth printers:** Linux host with kernel `AF_BLUETOOTH` support;
  printer paired on the host before adding to HA. See [Bluetooth (RFCOMM) printers](#bluetooth-rfcomm-printers).

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

## Bluetooth (RFCOMM) printers

Cheap thermal printers (Netum, MUNBYN, POS-58 generics, Phomemo Classic
line, etc.) connect over **Bluetooth Classic / RFCOMM**. This integration
opens a raw RFCOMM socket to a printer that's already paired on the host.

### Quickstart

> **TL;DR**: pair on the host, add it in HA, done. ~60 seconds.

1. **Pair the printer on the host** (HA OS users: Settings → Devices &
   services → Bluetooth, then put printer into pairing mode and accept).
   Otherwise, on the host shell:
   ```bash
   bluetoothctl
   [bluetooth]# scan on
   [bluetooth]# pair AA:BB:CC:DD:EE:FF
   [bluetooth]# trust AA:BB:CC:DD:EE:FF
   ```
2. **Add the printer in HA**: Settings → Devices & services → Add
   integration → *ESC/POS Thermal Printer* → **Bluetooth (RFCOMM)**.
   Pick your printer from the dropdown. The integration auto-filters to
   imaging-class devices so you won't see your phone or AirPods.
3. **Send a test print** from Developer Tools → Services:
   ```yaml
   service: escpos_printer.print_text
   data:
     target: notify.your_printer_entity
     text: "Hello from Home Assistant"
     cut: full
   ```

If your printer doesn't show up in step 2, see [No paired devices found](#no-paired-devices-found).
If you're running HA Container, see [Home Assistant Container](#home-assistant-container)
for the docker-compose changes you need.

### Bluetooth section contents

- [Quickstart](#quickstart)
- [How pairing works](#how-pairing-works)
- [Adding the printer in HA](#adding-the-printer-in-ha)
- [Battery sensor](#battery-sensor)
- [No paired devices found](#no-paired-devices-found)
- [Home Assistant Container](#home-assistant-container)
- [Host bridge fallback (`socat`)](#host-bridge-fallback-socat)
- [Security considerations](#security-considerations)
- [Troubleshooting](docs/TROUBLESHOOTING.md#bluetooth-connection-issues)

### How pairing works

The integration **does not pair devices itself**. Pair on the host once,
trust the device, then HA picks it up. The integration only opens an
`AF_BLUETOOTH` RFCOMM socket once paired — pairing UX (PIN entry,
agent registration) is the host OS's job.

- **HA OS / Supervised**: Settings → Devices & services → Bluetooth.
- **HA Core / Container with host bluez**:
  ```bash
  bluetoothctl
  [bluetooth]# scan on
  [bluetooth]# pair AA:BB:CC:DD:EE:FF     # your printer's MAC
  [bluetooth]# trust AA:BB:CC:DD:EE:FF
  ```
  On HA Container, pair from the **host** OS — not inside the
  container.
- Most ESC/POS printers pair without a PIN or accept `0000`. Note
  the [Security considerations](#security-considerations) about what
  that means.

### Adding the printer in HA

Settings → Devices & services → Add integration → *ESC/POS Thermal
Printer* → **Bluetooth (RFCOMM)**. Paired devices are listed
automatically when bluez D-Bus is reachable; otherwise the flow drops
to manual MAC entry.

The dropdown filters to imaging-class Bluetooth devices by default so
your phone and headset don't clutter the list. If your printer doesn't
advertise the Class-of-Device correctly (some cheap models don't), pick
**Show all paired Bluetooth devices** from the dropdown. Or use
**Manual MAC entry** if you already know the address.

The **RFCOMM channel** is hidden by default — almost every ESC/POS
printer uses channel 1. If the connection test fails with "channel
refused" you'll be prompted for a different one. Power users can also
enable HA's *Advanced Mode* in their profile to surface the field
up-front.

### Battery sensor

Portable / battery-powered BT printers (Phomemo M02, newer Netum
firmware, some Cashino models) expose battery level via bluez. When
present, a `sensor.{printer}_battery` entity surfaces it as a regular
HA battery sensor — automate "low battery" alerts on it. If your
printer doesn't expose `org.bluez.Battery1` (most cheap models don't),
the entity stays unavailable and you can ignore it.

### No paired devices found

If the picker shows the **No paired Bluetooth printers found** screen:

- The host can't see any paired BT devices, *or*
- bluez D-Bus isn't reachable from the HA process (most likely on HA
  Container without `/run/dbus` mounted, or rootless Docker).

Pair the printer first using the steps in [How pairing works](#how-pairing-works),
or — if you already know the MAC — submit the form to enter it
manually. The data plane works without bluez D-Bus as long as
`AF_BLUETOOTH` is reachable.

### Home Assistant Container

HA Container needs the host's Bluetooth stack exposed for the BT printer
flow:

```yaml
# docker-compose.yml
services:
  homeassistant:
    image: ghcr.io/home-assistant/home-assistant:stable
    network_mode: host          # required for AF_BLUETOOTH
    cap_add:
      - NET_ADMIN
      - NET_RAW
    volumes:
      - /run/dbus:/run/dbus:ro  # only needed for paired-device discovery
      - ./config:/config
    restart: unless-stopped
```

These settings substantially weaken Docker's isolation — see
[Security considerations](#security-considerations) before adopting
them. **If you care about container isolation, use the
[`socat` host bridge](#host-bridge-fallback-socat) instead.**

**Rootless Docker / Podman** is not supported because of a known D-Bus
EXTERNAL-auth limitation; use the host bridge.

### Host bridge fallback (`socat`)

If exposing bluez D-Bus to your container isn't workable, run `socat`
on the host as a one-line bridge and use the integration's existing
**Network (TCP/IP)** flow instead — zero new code path, no privilege
grants:

```bash
# Install socat once: apt install socat
socat TCP-LISTEN:9100,reuseaddr,fork BLUETOOTH-RFCOMM:AA:BB:CC:DD:EE:FF:1 &
```

Add the printer in HA as a network printer at `127.0.0.1:9100`.

### Security considerations

Bluetooth Classic / RFCOMM has security properties you should
understand before routing sensitive notifications to a paired printer:

- **The radio link is not encrypted by default.** Most ESC/POS thermal
  printers pair with no PIN or with `0000`, both of which negotiate a
  "Just Works" link key. ESC/POS bytes are recoverable over the air
  with consumer-grade SDR / Ubertooth equipment within ~10 metres.
  **Avoid routing OTPs, 2FA codes, door-access logs, alarm-disarm
  codes, or other sensitive content to a Bluetooth printer.**
- **Pairing is not authentication.** An attacker who can spoof your
  printer's MAC (`bdaddr -i hci0 AA:BB:CC:DD:EE:FF`) and listen on
  RFCOMM channel 1 will receive every print HA sends while the real
  printer is off or out of range. If integrity matters, prefer wired
  (USB) or a network printer on a trusted VLAN. Re-pair after any
  factory reset, theft, or extended absence.
- **Container exposure trade-off.** The docker-compose settings in
  [Home Assistant Container](#home-assistant-container) remove
  Docker's network-namespace isolation, grant raw-socket / iptables /
  route-table powers, and expose the system D-Bus protocol (`:ro` only
  protects the socket *file*, not bus messages). A vulnerability in
  any HA integration becomes more impactful in this configuration.
  Prefer the [`socat` host bridge](#host-bridge-fallback-socat) when
  isolation matters.
- **Status polling competes with prints.** Bluetooth Classic accepts
  one client at a time, so each status check is a real RFCOMM open
  and many cheap printers audibly beep on every connect. Set **Status
  check interval** to **60 seconds or longer** (or leave at `0` and
  rely on print success/failure for liveness). Aggressive polling
  beeps the printer, drains battery on portable models, and contends
  with in-flight print jobs.

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
