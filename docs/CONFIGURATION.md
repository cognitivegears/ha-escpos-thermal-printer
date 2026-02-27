# Configuration Guide

This guide covers all configuration options for the ESC/POS Thermal Printer integration.

## Table of Contents

- [Initial Setup](#initial-setup)
- [Configuration Options](#configuration-options)
- [Printer Profiles](#printer-profiles)
- [Service Parameters](#service-parameters)
- [Multiple Printers](#multiple-printers)

---

## Initial Setup

### Adding a Printer

1. Go to **Settings** > **Devices & services** > **Add Integration**
2. Search for "ESC/POS Thermal Printer"
3. Enter the connection details

### Connection Settings (Step 1)

| Setting | Description | Default |
|---------|-------------|---------|
| Host | IP address or hostname of your printer | Required |
| Port | TCP port number | 9100 |
| Timeout | Connection timeout in seconds | 4.0 |
| Printer Profile | Your printer model (see [Printer Profiles](#printer-profiles)) | Auto-detect |

### Printer Settings (Step 2)

| Setting | Description | Default |
|---------|-------------|---------|
| Codepage | Character encoding | Depends on profile |
| Line Width | Characters per line | Depends on profile |
| Default Alignment | Text alignment for all print jobs | left |
| Default Cut Mode | Paper cutting after print jobs | none |

### Finding Your Printer's IP Address

Most thermal printers can print a network status page:

1. Turn off the printer
2. Hold the feed button while turning it on
3. The printer will print its network configuration
4. Look for the IP address on the printout

Alternatively, check your router's DHCP client list.

---

## Configuration Options

After initial setup, you can modify settings by clicking **Configure** on the integration.

### Printer Profile

Select your printer model from the dropdown. The profile determines:

- Available codepages
- Line width options
- Supported cut modes
- Other hardware capabilities

Choose "Auto-detect" if your printer isn't listed. Choose "Custom" to enter a profile name manually from the [escpos-printer-db](https://github.com/receipt-print-hq/escpos-printer-db).

### Timeout

Connection timeout in seconds. Increase this if you have:

- A slow network connection
- A printer that takes time to wake up
- Intermittent connection issues

Typical values: 2-10 seconds.

### Codepage

Character encoding for text. Common options:

| Codepage | Use Case |
|----------|----------|
| CP437 | US English, box drawing characters |
| CP850 | Western European |
| CP852 | Central European |
| CP858 | Western European with Euro symbol |
| CP1252 | Windows Western European |
| ISO-8859-1 | Latin-1 |
| ISO-8859-15 | Latin-9 (with Euro symbol) |

The dropdown only shows codepages supported by your selected printer profile.

**Tip:** If special characters print incorrectly, try a different codepage or use the `print_text_utf8` service.

### Line Width

Characters per line. Common values:

| Width | Printer Type |
|-------|--------------|
| 32 | 58mm paper, small font |
| 42 | 80mm paper, small font |
| 48 | 80mm paper, normal font |
| 64 | 80mm paper, condensed font |

### Default Alignment

Applied when a service call doesn't specify alignment:

- `left` - Left-aligned (default)
- `center` - Centered
- `right` - Right-aligned

### Default Cut Mode

Applied when a service call doesn't specify cut mode:

- `none` - No cutting (default)
- `partial` - Partial cut (leaves a small connection)
- `full` - Full cut

### Keep Alive (Experimental)

Maintains a persistent connection to the printer. This can:

- Reduce print latency
- Cause issues if the printer goes offline

Leave disabled unless you have a specific need.

### Status Interval

How often to check if the printer is online (in seconds). Set to 0 to disable.

When enabled, the integration creates a binary sensor showing printer status.

---

## Printer Profiles

Printer profiles define hardware capabilities. The integration includes 35+ profiles from the [escpos-printer-db](https://github.com/receipt-print-hq/escpos-printer-db).

### Supported Brands

- Epson (TM-T20, TM-T88, TM-U220, etc.)
- Star Micronics (TSP100, TSP650, etc.)
- Citizen (CT-S series)
- Bixolon
- Samsung/Bixolon
- Partner Tech
- Generic ESC/POS

### Auto-detect Profile

The "Auto-detect" option uses generic ESC/POS commands that work with most printers. Use this if:

- Your printer model isn't listed
- You're not sure which profile to use
- You have a generic/unbranded printer

### Custom Profile

Select "Custom" to enter a profile name from escpos-printer-db manually. This is useful if your printer is in the database but not in the dropdown.

---

## Service Parameters

### escpos_printer.print_text

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| text | string | Yes | Text to print |
| align | string | No | `left`, `center`, `right` |
| bold | boolean | No | Bold text |
| underline | string | No | `none`, `single`, `double` |
| width | string/int | No | `normal`, `double`, `triple`, or 1-8 in YAML |
| height | string/int | No | `normal`, `double`, `triple`, or 1-8 in YAML |
| encoding | string | No | Override codepage |
| cut | string | No | `none`, `partial`, `full` |
| feed | integer | No | Lines to feed (0-10) |

### escpos_printer.print_text_utf8

Same as `print_text` but automatically converts UTF-8 characters to printer-compatible encoding. Does not accept the `encoding` parameter.

### escpos_printer.print_message

Entity service for the notify platform. Targets a notify entity and supports all text formatting options plus optional UTF-8 transcoding.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| message | string | Yes | Text to print |
| title | string | No | Title printed before the message |
| align | string | No | `left`, `center`, `right` |
| bold | boolean | No | Bold text |
| underline | string | No | `none`, `single`, `double` |
| width | string/int | No | `normal`, `double`, `triple`, or 1-8 in YAML |
| height | string/int | No | `normal`, `double`, `triple`, or 1-8 in YAML |
| utf8 | boolean | No | Enable UTF-8 transcoding |
| encoding | string | No | Override codepage (ignored when utf8 is true) |
| cut | string | No | `none`, `partial`, `full` |
| feed | integer | No | Lines to feed (0-10) |

### escpos_printer.print_qr

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| data | string | Yes | Data to encode |
| size | integer | No | Size 1-16 (default: 3) |
| ec | string | No | Error correction: `L`, `M`, `Q`, `H` |
| align | string | No | `left`, `center`, `right` |
| cut | string | No | `none`, `partial`, `full` |
| feed | integer | No | Lines to feed (0-10) |

### escpos_printer.print_barcode

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| code | string | Yes | Barcode data |
| bc | string | Yes | Barcode type |
| height | integer | No | Height in dots (1-255) |
| width | integer | No | Width multiplier (2-6) |
| pos | string | No | Text position: `ABOVE`, `BELOW`, `BOTH`, `OFF` |
| font | string | No | Text font: `A`, `B` |
| align_ct | boolean | No | Center the barcode |
| check | boolean | No | Validate checksum |
| force_software | string | No | Rendering mode |
| cut | string | No | `none`, `partial`, `full` |
| feed | integer | No | Lines to feed (0-10) |

**Supported barcode types:** EAN13, EAN8, UPC-A, UPC-E, CODE39, CODE93, CODE128, ITF, CODABAR

### escpos_printer.print_image

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| image | string | Yes | URL or local path |
| high_density | boolean | No | High-density mode (default: true) |
| align | string | No | `left`, `center`, `right` |
| cut | string | No | `none`, `partial`, `full` |
| feed | integer | No | Lines to feed (0-10) |

### escpos_printer.feed

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| lines | integer | Yes | Lines to feed (1-10) |

### escpos_printer.cut

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| mode | string | Yes | `full` or `partial` |

### escpos_printer.beep

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| times | integer | No | Number of beeps (default: 2) |
| duration | integer | No | Beep duration (default: 4) |

---

## Multiple Printers

### Adding Additional Printers

Add the integration multiple times, once for each printer:

1. **Settings** > **Devices & services** > **Add Integration**
2. Search for "ESC/POS Thermal Printer"
3. Enter the new printer's connection details

Each printer gets its own device and entities.

### Targeting Printers

When calling services, use the `target` parameter to specify which printer(s):

```yaml
# Single printer by device ID
target:
  device_id: abc123

# Multiple printers
target:
  device_id:
    - printer1_id
    - printer2_id

# By area
target:
  area_id: kitchen

# By entity
target:
  entity_id: binary_sensor.office_printer_online
```

Omit `target` to broadcast to all printers.

### Finding Device IDs

1. Go to **Settings** > **Devices & services**
2. Click on "ESC/POS Thermal Printer"
3. Click on your printer
4. The device ID is in the URL: `/config/devices/device/DEVICE_ID_HERE`

### Assigning Printers to Areas

1. Go to **Settings** > **Devices & services**
2. Click on your printer device
3. Click the pencil icon to edit
4. Select an area from the dropdown

This lets you target printers by area in service calls.
