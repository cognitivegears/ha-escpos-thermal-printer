# ESC/POS Thermal Printer for Home Assistant

![Validate](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/validate.yml/badge.svg)
![Hassfest](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hassfest.yml/badge.svg)
![HACS Validation](https://github.com/cognitivegears/ha-escpos-thermal-printer/actions/workflows/hacs.yml/badge.svg)

A Home Assistant integration for ESC/POS thermal printers that enables printing text, QR codes, barcodes, images, and more through automation.

![Printed Receipt Example](docs/assets/receipt.png)

The above is an example receipt printed using this integration.

## Features

- **UI Configuration** - No YAML required, easy setup through Home Assistant UI
- **Multiple Printer Support** - Configure multiple printers and target them individually or broadcast to all
- **Multiple Print Services** - Text, QR codes, barcodes, images, paper feed, cutting, and buzzer control
- **Notify Integration** - Send messages as printed receipts through Home Assistant notifications
- **Network Printer Support** - Works with any ESC/POS compatible thermal printer on your network
- **Flexible Formatting** - Support for text alignment, bold, underline, font sizes, and custom encoding
- **UTF-8 Transcoding** - Automatic conversion of UTF-8 text to printer-compatible encodings with smart character mapping
- **Dynamic Printer Profiles** - Select from 35+ printer models with automatic codepage and feature detection

## Requirements

### System Requirements

- **Home Assistant**: 2024.8 or later
- **Network Printer**: ESC/POS compatible thermal printer reachable on TCP port 9100 (default)
- **Network Connectivity**: Printer must be accessible from your Home Assistant instance

## Installation

### Method 1: HACS (Recommended)

1. **Install HACS** (if not already installed):
   - Open Home Assistant and go to **Settings** → **Add-ons, Backups & Supervisor** → **Add-on Store**
   - Search for "HACS" and install it following the official [HACS installation guide](https://hacs.xyz/docs/setup/download)

2. **Add Custom Repository**:
   - In HACS, go to **Settings** → **Custom repositories**
   - Add this repository: `https://github.com/cognitivegears/ha-escpos-thermal-printer`
   - Select **Integration** as the category

3. **Install the Integration**:
   - Go to **HACS** → **Integrations**
   - Search for "ESC/POS Thermal Printer"
   - Click **Download** and restart Home Assistant when prompted

4. **Configure the Integration**:
   - Go to **Settings** → **Devices & services** → **Add Integration**
   - Search for "ESC/POS Thermal Printer" and select it
   - Follow the configuration steps below

### Method 2: Manual Installation

1. **Download the Integration**:
   - Clone or download this repository to any temporary folder on your machine, then copy only the component folder into Home Assistant:

   ```bash
   # On your workstation or HA host shell
   git clone https://github.com/cognitivegears/ha-escpos-thermal-printer.git
   cp -R ha-escpos-thermal-printer/custom_components/escpos_printer /config/custom_components/
   ```

2. **Restart Home Assistant**:
   - Go to **Settings** → **System** → **Restart** to load the new integration

3. **Configure the Integration**:
   - Follow the configuration steps in the next section

## Configuration

### Initial Setup

1. **Add the Integration**:
   - Go to **Settings** → **Devices & services** → **Add Integration**
   - Search for "ESC/POS Thermal Printer" and click it

2. **Configure Printer Connection** (Step 1):
   - **Host**: IP address or hostname of your thermal printer (e.g., `192.168.1.100`)
   - **Port**: TCP port for the printer (default: `9100`)
   - **Timeout**: Connection timeout in seconds (default: `4.0`)
   - **Printer Profile**: Select your printer model from 35+ supported profiles, or use "Auto-detect" for generic printers. Choose "Custom" to enter a profile name manually from escpos-printer-db.

3. **Configure Printer Settings** (Step 2):
   - **Codepage**: Character encoding for your printer, filtered by the selected profile. Common options include CP437 (US), CP1252 (Western European), and many others.
   - **Line Width**: Characters per line, automatically suggested based on printer profile
   - **Default Alignment**: Default text alignment (`left`, `center`, or `right`)
   - **Default Cut Mode**: Default paper cutting behavior, filtered by printer capabilities

4. **Test the Connection**:
   - The integration will automatically test the connection during setup
   - If successful, you'll see a new device and services in your integration list

### Advanced Configuration Options

After initial setup, you can modify additional settings:

1. **Access Options**:
   - Go to **Settings** → **Devices & services**
   - Find your ESC/POS printer and click **Configure**

2. **Available Options**:
   - **Printer Profile**: Change printer model (resets codepage and line width to profile defaults)
   - **Timeout**: Adjust connection timeout (useful for slower networks)
   - **Codepage**: Set character encoding for international characters (filtered by profile)
   - **Line Width**: Characters per line (filtered by profile fonts)
   - **Default Alignment**: Set default text alignment for all print jobs
   - **Default Cut Mode**: Configure automatic paper cutting behavior (filtered by profile capabilities)
   - **Keep Alive**: Maintain persistent connection to printer (experimental)
   - **Status Interval**: Enable periodic printer status checks (seconds, 0 = disabled)

## Printer Setup

### Network Configuration

1. **Connect to Network**:
   - Connect the printer to your network using Ethernet cable
   - Power on the printer and wait for initialization

2. **Find Printer IP Address**:
   - Print a network configuration receipt (usually by holding the feed button during power-on)
   - Look for the IP address on the printed receipt

### Supported Printers

This integration should work with any printer supported by the [python-escpos library](https://python-escpos.readthedocs.io/en/latest/). Popular supported models include:

- **Epson**: TM-20, TM-88, TM-T20, TM-T70, TM-T88, TM-U220, TM-U295
- **Star Micronics**: TSP100, TSP650, TSP700, TSP800, SP500, SP700
- **Citizen**: CT-S2000, CT-S4000, CT-S601, CT-S651, CT-S801, CT-S851
- **And many more...**

For a complete list, see the [python-escpos documentation](https://python-escpos.readthedocs.io/en/latest/user/printers.html).

## Usage

### Basic Usage

#### Print Text

```yaml
service: escpos_printer.print_text
data:
  text: "Hello, World!"
  align: center
  bold: true
  cut: partial
  feed: 2
```

#### Print QR Code

```yaml
service: escpos_printer.print_qr
data:
  data: "https://www.home-assistant.io"
  size: 8
  ec: M
  align: center
  cut: partial
```

#### Print UTF-8 Text

```yaml
service: escpos_printer.print_text_utf8
data:
  text: "Café résumé — "smart quotes" and ellipsis…"
  align: center
  bold: true
  cut: partial
```

This service is ideal when your text source (such as templates, sensors, or external APIs) contains UTF-8 characters that aren't directly supported by your printer's codepage.

#### Print Image

```yaml
service: escpos_printer.print_image
data:
  image: "/config/www/logo.png"
  align: center
  cut: partial
  feed: 1
```

### Device Targeting (Multiple Printers)

When you have multiple printers configured, you can target specific printers or broadcast to all of them.

#### Using the UI (Developer Tools)

1. Go to **Developer Tools** → **Actions**
2. Select any `escpos_printer.*` service
3. Click **Choose device** to select one or more printers
4. Fill in the service parameters and click **Perform action**

The device picker will only show ESC/POS printer devices from this integration.

#### Targeting a Specific Printer (YAML)

Use the `target` parameter with `device_id` to send to a specific printer:

```yaml
service: escpos_printer.print_text
target:
  device_id: abc123def456  # Your printer's device ID
data:
  text: "Hello from Kitchen Printer!"
  cut: partial
```

You can find your printer's device ID in **Settings** → **Devices & services** → **ESC/POS Thermal Printer** → click on your printer → the device ID is shown in the URL or device info.

#### Targeting Multiple Specific Printers

Target multiple printers by listing their device IDs:

```yaml
service: escpos_printer.print_text
target:
  device_id:
    - abc123def456  # Kitchen printer
    - xyz789ghi012  # Office printer
data:
  text: "Alert: System notification"
  bold: true
  cut: partial
```

#### Broadcast to All Printers

To print to all configured printers, simply omit the `target` parameter:

```yaml
service: escpos_printer.print_text
data:
  text: "Broadcast message to all printers!"
  align: center
  cut: partial
```

This is useful for announcements or alerts that should appear on every printer.

#### Targeting by Area

If your printers are assigned to areas, you can target by area:

```yaml
service: escpos_printer.print_text
target:
  area_id: kitchen
data:
  text: "Kitchen order ready!"
  cut: partial
```

#### Targeting by Entity

You can also target using the printer's binary sensor entity:

```yaml
service: escpos_printer.print_text
target:
  entity_id: binary_sensor.esc_pos_printer_192_168_1_100_9100_online
data:
  text: "Hello World!"
  cut: partial
```

### Advanced Usage Examples

#### Receipt Printing

```yaml
service: escpos_printer.print_text
data:
  text: |
    ====================================
               STORE RECEIPT
    ====================================

    Item 1.......................$10.00
    Item 2.......................$15.50
    ------------------------------------
    Total........................$25.50

    Thank you for your business!
  align: left
  cut: full
  feed: 3
```

#### Multi-format Receipt with QR Code

```yaml
# Print header
service: escpos_printer.print_text
data:
  text: "=== SMART HOME RECEIPT ==="
  align: center
  bold: true
  width: double
  height: double

# Print details
service: escpos_printer.print_text
data:
  text: |
    Date: {{ now().strftime('%Y-%m-%d %H:%M') }}
    Temperature: {{ states('sensor.temperature') }}°F
    Humidity: {{ states('sensor.humidity') }}%
  align: left

# Print QR code for feedback
service: escpos_printer.print_qr
data:
  data: "https://forms.example.com/feedback"
  size: 6
  align: center

# Print footer and cut
service: escpos_printer.print_text
data:
  text: "Scan QR code for feedback!"
  align: center
  cut: partial
  feed: 2
```

#### Print Barcode

```yaml
service: escpos_printer.print_barcode
data:
  code: "4006381333931"
  bc: "EAN13"
  height: 100
  width: 3
  align: center
  cut: partial
```

### Service Reference

#### `escpos_printer.print_text`

Print formatted text to the printer.

**Parameters:**

- `text` (required): Text to print (supports multiline with `|` in YAML)
- `align`: Text alignment (`left`, `center`, `right`)
- `bold`: Enable bold text (`true`/`false`)
- `underline`: Underline style (`none`, `single`, `double`)
- `width`: Font width (`normal`, `double`, `triple`)
- `height`: Font height (`normal`, `double`, `triple`)
- `encoding`: Character encoding override
- `cut`: Paper cutting (`none`, `partial`, `full`)
- `feed`: Lines to feed after printing (0-10)

#### `escpos_printer.print_text_utf8`

Print UTF-8 text with automatic transcoding to the printer's configured codepage. This service automatically converts special characters like curly quotes, em-dashes, and accented letters to their closest equivalents supported by the printer.

**Parameters:**

- `text` (required): UTF-8 text to print (special characters will be automatically converted)
- `align`: Text alignment (`left`, `center`, `right`)
- `bold`: Enable bold text (`true`/`false`)
- `underline`: Underline style (`none`, `single`, `double`)
- `width`: Font width (`normal`, `double`, `triple`)
- `height`: Font height (`normal`, `double`, `triple`)
- `cut`: Paper cutting (`none`, `partial`, `full`)
- `feed`: Lines to feed after printing (0-10)

**Character Conversion Examples:**
- Curly quotes (`"..."`, `'...'`) → straight quotes (`"..."`, `'...'`)
- Em-dashes (`—`) → double hyphen (`--`)
- Ellipsis (`…`) → three dots (`...`)
- Accented characters (e.g., `é`, `ñ`) → base letter if not in codepage
- Box drawing characters (CP437) → preserved when supported by codepage

#### `escpos_printer.print_qr`

Print a QR code.

**Parameters:**

- `data` (required): Data to encode in QR code
- `size`: QR code size (1-16, default: 3)
- `ec`: Error correction level (`L`, `M`, `Q`, `H`)
- `align`: QR code alignment (`left`, `center`, `right`)
- `cut`: Paper cutting (`none`, `partial`, `full`)
- `feed`: Lines to feed after printing (0-10)

#### `escpos_printer.print_image`

Print an image from URL or local path.

**Parameters:**

- `image` (required): Image URL or local path (e.g., `/config/www/image.png`)
- `high_density`: Use high-density printing (`true`/`false`)
- `align`: Image alignment (`left`, `center`, `right`)
- `cut`: Paper cutting (`none`, `partial`, `full`)
- `feed`: Lines to feed after printing (0-10)

#### `escpos_printer.feed`

Feed paper without printing.

**Parameters:**

- `lines` (required): Number of lines to feed (1-10)

#### `escpos_printer.cut`

Cut the paper.

**Parameters:**

- `mode` (required): Cut type (`full` or `partial`)

#### `escpos_printer.print_barcode`

Print a barcode.

**Parameters:**

- `code` (required): Barcode data
- `bc` (required): Barcode type (e.g., `EAN13`, `CODE128`, `UPCA`)
- `height`: Barcode height in dots (1-255)
- `width`: Barcode width (2-6)
- `pos`: Human-readable text position (`ABOVE`, `BELOW`, `BOTH`, `OFF`)
- `font`: Font for human-readable text (`A` or `B`)
- `align_ct`: Center alignment (`true`/`false`)
- `check`: Enable checksum (`true`/`false`)
- `force_software`: Rendering method
- `align`: Barcode alignment (`left`, `center`, `right`)
- `cut`: Paper cutting (`none`, `partial`, `full`)
- `feed`: Lines to feed after printing (0-10)

#### `escpos_printer.beep`

Sound the printer buzzer (if supported).

**Parameters:**

- `times`: Number of beeps (1-10)
- `duration`: Beep duration (1-10)

## Home Assistant Automations

### Door Access Logging

```yaml
automation:
  - alias: "Log Door Access"
    trigger:
      platform: state
      entity_id: binary_sensor.front_door
      to: "on"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            === DOOR ACCESS ===
            Time: {{ now().strftime('%H:%M:%S') }}
            Date: {{ now().strftime('%Y-%m-%d') }}
            Access: FRONT DOOR
            Status: OPENED
          align: center
          cut: partial
          feed: 1
```

### Temperature Alert Receipts

```yaml
automation:
  - alias: "Temperature Alert"
    trigger:
      platform: numeric_state
      entity_id: sensor.temperature
      above: 80
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            !! TEMPERATURE ALERT !!
            Current: {{ states('sensor.temperature') }}°F
            Time: {{ now().strftime('%H:%M') }}
            Location: Living Room
          align: center
          bold: true
          cut: partial
          feed: 2
```

### Daily Summary Report

```yaml
automation:
  - alias: "Daily Summary Report"
    trigger:
      platform: time
      at: "08:00:00"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            === DAILY SUMMARY ===
            Date: {{ now().strftime('%Y-%m-%d') }}

            Temperature Range:
            Min: {{ state_attr('sensor.temperature_daily', 'min_value') }}°F
            Max: {{ state_attr('sensor.temperature_daily', 'max_value') }}°F
            Avg: {{ state_attr('sensor.temperature_daily', 'average') }}°F

            System Status: {{ states('binary_sensor.system_healthy') }}
          align: left
          cut: full
          feed: 3
```

### Notification Integration

```yaml
automation:
  - alias: "Print Notifications"
    trigger:
      platform: event
      event_type: call_service
      event_data:
        domain: notify
        service: send_message
    condition:
      condition: template
      value_template: "{{ trigger.event.data.service_data.entity_id == 'notify.esc_pos_printer_192_168_1_100_9100' }}"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            - NOTIFICATION -
            {{ trigger.event.data.service_data.message }}
            ---
            {{ now().strftime('%H:%M %m/%d/%Y') }}
          align: center
          cut: partial
          feed: 1
```

### Multi-Printer Automation Examples

#### Kitchen Order System (Targeted Printing)

Print orders to a specific kitchen printer:

```yaml
automation:
  - alias: "Kitchen Order Ticket"
    trigger:
      platform: event
      event_type: new_order
    action:
      - service: escpos_printer.print_text
        target:
          device_id: kitchen_printer_device_id  # Target only the kitchen printer
        data:
          text: |
            === KITCHEN ORDER ===
            Order #{{ trigger.event.data.order_id }}
            Time: {{ now().strftime('%H:%M') }}

            {{ trigger.event.data.items }}

            =====================
          align: left
          bold: true
          cut: full
          feed: 2
```

#### Emergency Broadcast (All Printers)

Send urgent messages to all printers simultaneously:

```yaml
automation:
  - alias: "Emergency Alert All Printers"
    trigger:
      platform: state
      entity_id: binary_sensor.emergency_alert
      to: "on"
    action:
      - service: escpos_printer.print_text
        # No target = broadcast to ALL configured printers
        data:
          text: |
            !!! EMERGENCY ALERT !!!

            {{ states('input_text.emergency_message') }}

            Time: {{ now().strftime('%H:%M:%S') }}
            !!! TAKE ACTION NOW !!!
          align: center
          bold: true
          width: double
          height: double
          cut: partial
          feed: 3
```

#### Location-Based Printing (Area Targeting)

Print to all printers in a specific area:

```yaml
automation:
  - alias: "Office Announcement"
    trigger:
      platform: time
      at: "09:00:00"
    action:
      - service: escpos_printer.print_text
        target:
          area_id: office  # All printers in the "office" area
        data:
          text: |
            === DAILY BRIEFING ===
            {{ now().strftime('%A, %B %d, %Y') }}

            Today's meetings:
            {{ states('sensor.calendar_meetings') }}
          align: left
          cut: partial
          feed: 2
```

#### Multi-Location Receipt (Multiple Specific Printers)

Print to multiple specific printers (e.g., customer receipt + kitchen copy):

```yaml
automation:
  - alias: "Order Confirmation Multi-Print"
    trigger:
      platform: event
      event_type: order_placed
    action:
      # Print to both front desk and kitchen
      - service: escpos_printer.print_text
        target:
          device_id:
            - front_desk_printer_id
            - kitchen_printer_id
        data:
          text: |
            Order #{{ trigger.event.data.order_number }}
            {{ trigger.event.data.items }}
            Total: ${{ trigger.event.data.total }}
          cut: partial
```

## Notification Usage

The integration creates a notification entity that allows you to send messages as printed receipts:

1. **Find the Notify Entity**:
   - Go to **Developer Tools** → **Actions**
   - Look for entities starting with `notify.esc_pos_printer_`

2. **Send a Notification**:

   ```yaml
   service: notify.send_message
   data:
     entity_id: notify.esc_pos_printer_192_168_1_100_9100
     message: "Hello from Home Assistant!"
   ```

3. **Advanced Notification**:

   ```yaml
   service: notify.send_message
   data:
     entity_id: notify.esc_pos_printer_192_168_1_100_9100
     message: |
       !! System Alert !!
       {{ states('sensor.temperature') }}°F
       {{ now().strftime('%H:%M') }}
     title: "Temperature Alert"
   ```

## Troubleshooting

### Common Issues and Solutions

#### Connection Problems

**Issue**: "Cannot connect to printer"
**Solutions**:

- Verify the printer IP address and port (9100 is default)
- Check network connectivity between Home Assistant and printer
- Ensure the printer is powered on and connected to the network
- Try increasing the timeout value in integration options
- Test connectivity with: `telnet <PRINTER_IP> 9100`

#### Print Quality Issues

**Issue**: "Text appears garbled or incorrect characters"
**Solutions**:

- Set the correct codepage in integration options (e.g., `cp437` for English, `cp1252` for Western European)
- Ensure the printer supports the selected codepage
- **Use `print_text_utf8` service** for text containing special characters (curly quotes, em-dashes, accented letters, etc.) - it automatically converts UTF-8 to your printer's codepage
- Try different encoding options in service calls

#### Image Printing Problems

**Issue**: "Images are too wide or distorted"
**Solutions**:

- Resize images to maximum 512 pixels width
- Use PNG or JPEG formats (avoid BMP if possible)
- Enable/disable `high_density` option based on your printer model
- Check printer DPI settings

#### Paper Cutting Issues

**Issue**: "Paper doesn't cut properly"
**Solutions**:

- Verify your printer supports automatic cutting
- Try `partial` cut instead of `full` cut
- Check paper type and ensure it's loaded correctly
- Some printers require manual cutting

#### Service Not Found

**Issue**: "Service 'escpos_printer.*' not found"
**Solutions**:

- Restart Home Assistant after installation
- Verify the integration is properly loaded in **Settings** → **Devices & services**
- Check Home Assistant logs for integration errors

### Debug Logging

Enable debug logging to troubleshoot issues:

1. **Add to configuration.yaml**:

   ```yaml
   logger:
     logs:
       escpos: debug
       custom_components.escpos_printer: debug
   ```

2. **Restart Home Assistant** and check logs in **Settings** → **System** → **Logs**

### Printer-Specific Issues

#### Epson TM Series

- Ensure printer is in ESC/POS mode (not Epson proprietary mode)
- Check DIP switch settings for network configuration
- Update printer firmware to latest version

#### Star Micronics

- Verify correct emulation mode (ESC/POS)
- Check interface settings in printer configuration
- Ensure proper driver installation on network interface

#### Generic ESC/POS

- Test with minimal ESC/POS commands first
- Verify printer supports raw TCP printing
- Check manufacturer documentation for ESC/POS compatibility

### Getting Help

If you continue to have issues:

1. **Check Existing Issues**: Search [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues) for similar problems
2. **Create a New Issue**: Include:
   - Your printer model and firmware version
   - Home Assistant version and installation method
   - Complete error logs with debug logging enabled
   - Steps to reproduce the issue
   - Your configuration (without sensitive information)

## Development

### Contributing

Contributions are welcome! See CONTRIBUTING.md for setup, coding standards, dependency policy (exact pins with uv + Renovate), and how to run local checks.

### Testing

Run the test suite:

```bash
python -m pytest tests/
```

### Local Testing with Docker

Run a local Home Assistant instance with the integration mounted:

```bash
# Start Home Assistant (access at http://localhost:8123)
docker compose up

# Run in background
docker compose up -d

# Stop and remove container
docker compose down
```

The Docker Compose setup mounts `custom_components/` into the container, so changes to your code are reflected on HA restart.

Once the container is running, open http://localhost:8123 in your browser. Complete the Home Assistant onboarding, then go to **Settings** → **Devices & services** → **Add Integration** and search for "ESC/POS Thermal Printer" to test the integration directly.

### Developer Utilities

- Framework smoke test (no Home Assistant required):

  ```bash
  python scripts/framework_smoke_test.py
  ```

### Building

This integration follows Home Assistant's integration structure. See the [Home Assistant Developer Documentation](https://developers.home-assistant.io/docs/creating_integration_file_structure) for details.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## References

- [Python-ESC/POS Library](https://github.com/python-escpos/python-escpos) - Core printing functionality
- [Python-ESC/POS Documentation](https://python-escpos.readthedocs.io/) - Detailed API documentation
- [Home Assistant Integration Development](https://developers.home-assistant.io/docs/creating_integration_file_structure) - Integration guidelines
- [HACS Documentation](https://hacs.xyz/) - Custom repository installation
- [Aaron Godfrey's HA Custom Component Series](https://www.youtube.com/playlist?list=PL9luKH1ZjSZtTlMNbSbhX0CCJsHQp7ZW) - Development tutorials

## Support

- **Issues**: [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues)
- **Discussions**: [GitHub Discussions](https://github.com/cognitivegears/ha-escpos-thermal-printer/discussions)
- **Documentation**: [GitHub Wiki](https://github.com/cognitivegears/ha-escpos-thermal-printer/wiki)
