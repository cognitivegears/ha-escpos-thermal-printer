# Serial (UART/RS-232) Printers

For printers connected via a physical serial cable or a network-based serial proxy such as ESPHome.

The integration supports four connection formats:

| Format | Example | Use case |
|--------|---------|----------|
| Device path | `/dev/ttyUSB0`, `/dev/ttyACM0`, `COM3` | Direct UART/RS-232 cable |
| `esphome://host:6053?port_name=Name` | `esphome://192.168.1.100:6053?port_name=Printer` | ESPHome UART proxy |
| `rfc2217://host:port` | `rfc2217://192.168.1.50:2217` | RFC 2217 serial server |
| `socket://host:port` | `socket://192.168.1.50:9100` | Raw TCP socket |

## Requirements

- **Direct serial (device path):** The Home Assistant host must have a serial port accessible at the path (USB-to-serial adapters show up as `/dev/ttyUSB0` or `/dev/ttyACM0` on Linux).
- **Serial port permissions on Linux:** The HA user must be in the `dialout` group (or `uucp` on some distributions):

  ```bash
  sudo usermod -aG dialout homeassistant
  ```

  Log out and back in (or restart HA) for the group change to take effect.
- **Docker:** Pass the serial device through to the container:

  ```yaml
  services:
    homeassistant:
      devices:
        - /dev/ttyUSB0:/dev/ttyUSB0
  ```

- **Network-based connections (ESPHome, RFC2217, socket):** No special permissions needed — the integration connects over TCP.

## Configuration

| Setting | Description | Default |
|---------|-------------|---------|
| Serial port | Device path (e.g. `/dev/ttyUSB0`) or URL (e.g. `esphome://host:6053?port_name=Name`) | — |
| Baud rate | Serial speed for the serial connection. | 9600 |
| Timeout | Connection timeout in seconds | 4.0 |
| Printer Profile | Your printer model (or Auto-detect) | Auto-detect |
| Codepage | Character encoding (or Auto-detect) | Auto-detect |
| Line width | Characters per line (32 for 58 mm, 42–48 for 80 mm) | 48 |

## ESPHome serial proxy

The most common networked-serial use case: an ESP32/ESP8266 bridging a UART-connected printer to your network. Add a `uart:` block and a `serial_proxy:` to your device's YAML, then use the ESPHome URL format as the serial port.

### Example ESPHome configuration

```yaml
uart:
  tx_pin: 18
  rx_pin: 19
  baud_rate: 9600
  id: printer

serial_proxy:
  - name: Printer
    uart_id: printer
    port_type: TTL
```

### Connecting in HA

In the serial port field, enter:

```text
esphome://host:6053?port_name=Name
```

Replace `host` with the ESP device's IP and `Name` with the proxy name you configured. The **baud rate** setting in HA is used to override the rate set in the ESPHome configuration.

If your ESPHome device uses API encryption, append `&key=<base64-psk>` to the URL (e.g. `esphome://host:6053?port_name=Name&key=...`). The full URL (including the key) is stored in the HA config entry and redacted automatically in diagnostics downloads.

### Write chunk size and inter-chunk delay

ESP32 UART FIFOs are small (128 bytes). When the integration sends a large print job the ESP32 can drop bytes if data arrives faster than it can drain the buffer, causing garbled or truncated output and may result in crashing the ESP32 entirely.

To work around this, set the **Write chunk size** and **Inter-chunk delay** options in the integration's settings:

| Option | Recommended value | Description |
|--------|-------------------|-------------|
| Write chunk size | `128` | Maximum bytes sent per write call |
| Inter-chunk delay (ms) | `10` | Pause between chunks so the device can drain its buffer |

These options are available under **Settings → Devices & services → ESC/POS Thermal Printer → Configure**.

## Direct UART / RS-232

For printers with a physical RS-232 or TTL serial port connected directly to the HA host (or via a USB-to-serial adapter):

1. Find the port path:

   ```bash
   ls /dev/ttyUSB* /dev/ttyACM*
   # or, for a more descriptive listing:
   ls -l /dev/serial/by-id/
   ```

2. Find the right baud rate — check your printer's manual or print a self-test page (hold the feed button while powering on). Common rates: 9600, 19200, 38400, 115200.
3. In the integration setup, enter the device path (e.g. `/dev/ttyUSB0`) and select the baud rate.

## Troubleshooting

### "Permission denied accessing serial port"

The HA process can't open the device node. On Linux, add the HA user to the `dialout` group:

```bash
sudo usermod -aG dialout homeassistant
```

Restart Home Assistant for the change to take effect.

### "Serial port not found"

The device path doesn't exist on the host. Verify with:

```bash
ls /dev/ttyUSB* /dev/ttyACM*
```

For URL-based connections, confirm the ESPHome device / RFC2217 server is online and reachable.

### "Serial port is busy"

Another process holds the port. Common culprits on Linux are **ModemManager** and **brltty** (Braille TTY), which claim USB-serial adapters automatically:

```bash
# Disable ModemManager (if not needed)
sudo systemctl disable --now ModemManager

# Or tell udev to ignore the device:
# /etc/udev/rules.d/99-escpos-serial.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="<VID>", ATTRS{idProduct}=="<PID>", ENV{ID_MM_DEVICE_IGNORE}="1"
```

### Garbled or truncated output (ESPHome/ESP32)

The ESP32 is dropping bytes due to UART buffer overruns. Enable write chunking — see [Write chunk size and inter-chunk delay](#write-chunk-size-and-inter-chunk-delay) above.

### Status shows "Unknown" until first print

The binary sensor for serial printers works by checking whether the device path exists and is a character device. For URL-based connections (ESPHome, RFC2217) it makes a brief test connection. If **Status check interval** is `0` (the default), no periodic check runs and the status remains unknown until something is printed. Set **Status check interval** to a non-zero value (e.g. 60 seconds) to enable periodic checks.

See [troubleshooting.md](troubleshooting.md#serial-issues) for more.
