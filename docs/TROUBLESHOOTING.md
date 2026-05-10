# Troubleshooting

Solutions for common issues with the ESC/POS Thermal Printer integration.

## Table of Contents

- [Connection Issues](#connection-issues)
- [USB Connection Issues](#usb-connection-issues)
- [Bluetooth Connection Issues](#bluetooth-connection-issues)
- [Print Quality Problems](#print-quality-problems)
- [Service Errors](#service-errors)
- [Image Issues](#image-issues)
- [Paper and Cutting](#paper-and-cutting)
- [Multiple Printers](#multiple-printers)
- [Debug Logging](#debug-logging)
- [Printer-Specific Issues](#printer-specific-issues)

---

## Connection Issues

### "Cannot connect to printer"

**Check network connectivity:**

```bash
# From the Home Assistant host or container
ping <PRINTER_IP>

# Test the printer port
telnet <PRINTER_IP> 9100
```

If telnet connects and shows a blank screen, the printer is reachable. Press
Ctrl+] then type `quit` to exit.

**Common causes:**

1. **Wrong IP address** - Print a network status page from your printer to
verify the IP
2. **Printer is off or sleeping** - Some printers enter sleep mode; try printing
a test page from the printer itself
3. **Firewall blocking port 9100** - Check firewall rules on your network
4. **Printer on different subnet** - Make sure Home Assistant can reach the
printer's network

**Solutions:**

- Increase the timeout value in integration options (try 8-10 seconds)
- Assign a static IP to your printer to prevent IP changes
- Check that port 9100 is not blocked by your router or firewall

### Connection works sometimes, fails other times

**Possible causes:**

- DHCP lease expiring and printer getting a new IP
- Printer entering sleep mode
- Network congestion or instability

**Solutions:**

- Assign a static IP address to the printer
- Disable sleep mode on the printer if possible
- Enable the "Keep Alive" option (experimental)
- Use the Status Interval option to detect when the printer goes offline

### "Connection refused"

The printer is reachable but rejecting connections.

**Check:**

- Another application might be using the printer
- The printer might have a connection limit
- The printer might be in an error state (paper out, cover open)

Try power cycling the printer.

---

## USB Connection Issues

### "Permission denied" / "Access denied"

The Home Assistant process doesn't have permission to access the USB device.

**On Linux (most HA installations):**

Create a udev rule to grant access:

```bash
# Create file: /etc/udev/rules.d/99-escpos.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", MODE="0666"
```

Replace `04b8` with your printer's vendor ID. Then reload:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

**On Home Assistant OS:**

USB access is typically allowed, but some devices may need additional configuration.
Try unplugging and re-plugging the printer, then restart Home Assistant.

**On Docker:**

Make sure the USB device is passed through to the container:

```yaml
devices:
  - /dev/bus/usb:/dev/bus/usb
```

Or pass the specific device (e.g., `/dev/usb/lp0`).

### "Device not found"

The printer is not detected via USB.

**Check:**

1. Printer is powered on and connected via USB
2. USB cable is working (try a different cable)
3. Verify the device appears in the system:
   ```bash
   # Linux
   lsusb | grep -i printer

   # Look for your printer's vendor ID (e.g., 04b8 for Epson)
   lsusb
   ```

### "Input/Output Error" (Errno 5)

You may see an error like:

```
usb.core.USBError: [Errno 5] Input/Output Error
```

This is libusb's generic I/O error. In python-escpos it can be raised during
USB open and then wrapped as a `DeviceNotFoundError`, so it can look like
"Device not found" even if the device was just detected.

**Common causes:**

- **Device reset or transient disconnect.** Some USB printers reset or briefly
  drop off the bus when waking up or during power management. The kernel docs
  note that some devices misbehave on autosuspend/resume, especially printers.
- **Another program or kernel driver has claimed the interface.** libusb
  cannot claim an interface if another app or a kernel driver already owns it.
  You may need to stop the other app or detach the kernel driver.

**Things to try:**

1. Replug the printer and retry the print.
2. Disable USB autosuspend for the device (see "USB printer works intermittently").
3. Ensure no other service is holding the device (e.g., other printing or
   monitoring tools), or detach the kernel driver where appropriate.

### "USB backend missing"

The libusb library is not installed.

**Solutions:**

- **Home Assistant OS:** libusb is included; try restarting HA
- **Docker:** Ensure libusb is in your container image
- **Linux:** Install libusb: `sudo apt install libusb-1.0-0`
- **macOS:** Install via Homebrew: `brew install libusb`

### "Cannot connect" with wrong endpoints

USB endpoint configuration is incorrect.

**Solutions:**

1. Try the default endpoints (in: 0x82, out: 0x01)
2. If those don't work, find correct endpoints:
   ```bash
   # Linux - find your device
   lsusb -v -d VENDOR:PRODUCT | grep Endpoint
   ```
3. Look for "bEndpointAddress" values - OUT endpoint for sending, IN for receiving

### Printer not auto-discovered

Your printer's vendor ID might not be in the known list.

**Solutions:**

1. Use **Browse all USB devices** when adding the printer
2. Use **Manual entry** with your printer's VID:PID
3. Find VID:PID using `lsusb` or Device Manager

### USB printer works intermittently

**Possible causes:**

- Power management putting the USB device to sleep
- Loose USB connection
- USB hub issues

**Solutions:**

1. Connect directly to the computer (not through a hub)
2. Use a powered USB hub if you must use a hub
3. Check USB cable quality
4. On Linux, disable USB autosuspend:
   ```bash
   echo -1 > /sys/bus/usb/devices/usb*/power/autosuspend
   ```

---

## Bluetooth Connection Issues

The Bluetooth (RFCOMM) flow is **pair-on-host**: the integration never
pairs devices itself, it only opens RFCOMM sockets to already-paired
printers. Most Bluetooth issues are pairing problems on the host or
permission/exposure problems with the bluez stack.

### Error key reference

When a Bluetooth print or status check fails, the integration shows one
of these error keys (visible in HA logs and on the config-flow form):

| Error key                  | Likely cause                                           | Action |
|----------------------------|--------------------------------------------------------|--------|
| `bt_unavailable`           | Kernel doesn't support `AF_BLUETOOTH` (or HA Container without `--net=host`) | See ["Bluetooth not available"](#bluetooth-not-available) below |
| `bt_permission_denied`     | HA process can't open the Bluetooth socket             | Add HA user to the `bluetooth` group on bare Linux; on HA OS this is preconfigured |
| `bt_device_not_found`      | Printer never paired, or paired entry was removed      | Pair the printer on the host (see README) |
| `bt_host_down`             | Printer powered off, out of range, or already connected to another host | Power on, bring closer, disconnect any other paired host |
| `bt_timeout`               | Printer asleep — first probe missed it                 | Print once to wake it, or increase the timeout |
| `bt_channel_refused`       | Printer reachable but RFCOMM channel wrong             | Try channel 1 (default for ESC/POS); confirm with `bluetoothctl info <MAC>` |
| `cannot_connect_bt`        | Generic catchall (errno not recognized)                | Check HA debug logs for the underlying errno |
| `invalid_bt_mac`           | MAC address format invalid                             | Use `AA:BB:CC:DD:EE:FF` (uppercase, colons) |
| `invalid_rfcomm_channel`   | Channel out of range                                   | Must be 1–30 (almost always 1) |

### Bluetooth not available

> "Bluetooth Classic (AF_BLUETOOTH/RFCOMM) is not available in this
> environment."

**Cause:** the kernel `AF_BLUETOOTH` socket family isn't reachable from
the HA process. Most common causes:

1. **HA Container without `--net=host`** — the default Docker network
   namespace doesn't expose `AF_BLUETOOTH`. See the docker-compose
   snippet in the README's [Home Assistant Container caveats] section.
2. **Rootless Docker / Podman** — the bluez D-Bus EXTERNAL auth doesn't
   work across UID namespaces. **Use the [`socat` host-bridge fallback]**
   from the README instead.
3. **Non-Linux host** — `AF_BLUETOOTH` is Linux-only. macOS / Windows
   HA installs cannot use this connection type natively; use the
   `socat` host-bridge or a network printer.

[Home Assistant Container caveats]: ../README.md#home-assistant-container-caveats
[`socat` host-bridge fallback]: ../README.md#host-bridge-fallback-socat

### "Bluetooth printer not reachable" (intermittent)

The status sensor flaps between online and offline. Most BT thermal
printers sleep aggressively to save battery, then wake on the next
RFCOMM connect — but the connect itself takes 1–3 seconds.

**Solutions:**

- **Set Status check interval to 60 seconds or longer** (or `0` to
  disable). Aggressive polling makes cheap printers beep on every probe
  and competes for the printer's only RFCOMM slot. See the README's
  [Security considerations] for the recommended floor.
- Run `bluetoothctl info <MAC>` on the host to confirm the printer is
  still paired and the link key is intact:
  ```bash
  bluetoothctl info AA:BB:CC:DD:EE:FF
  # Look for "Paired: yes" and "Trusted: yes"
  ```
- If the printer was factory-reset (or its battery fully drained), the
  link key may be invalidated. Re-pair:
  ```bash
  bluetoothctl
  [bluetooth]# remove AA:BB:CC:DD:EE:FF
  [bluetooth]# scan on
  [bluetooth]# pair AA:BB:CC:DD:EE:FF
  [bluetooth]# trust AA:BB:CC:DD:EE:FF
  ```

[Security considerations]: ../README.md#security-considerations

### "Connection refused" / `bt_channel_refused`

The printer is reachable but rejects the RFCOMM channel. Almost always
means the channel number is wrong.

**Solutions:**

- Default to **channel 1**. The vast majority of ESC/POS thermal
  printers expose SPP on channel 1.
- Confirm via SDP service-record lookup:
  ```bash
  bluetoothctl info AA:BB:CC:DD:EE:FF
  # Look for the SerialPort service-record entry — its "Channel:" line
  # is the value to use.
  ```
- If the printer presents multiple SPP records, try each channel in turn.

### Paired-device list is empty in the config flow

The bluez D-Bus enumeration succeeded but returned no devices, **or**
D-Bus wasn't reachable and the flow fell through to manual MAC entry.

**Verify:**

```bash
# On the host (HA OS: drop into the host shell first via `login`)
bluetoothctl paired-devices
```

- If `bluetoothctl paired-devices` shows your printer but the integration
  doesn't, the HA process can't reach the system D-Bus. On HA Container,
  add `/run/dbus:/run/dbus:ro` to your volume mounts (see README).
- If `bluetoothctl paired-devices` is also empty, the printer simply
  isn't paired — pair it first per the README instructions.

### Status sensor stale (timestamp not updating)

Status checks are deliberately **skipped while a print is in flight**
(RFCOMM accepts only one client at a time, so a probe during a print
would either fail or kick the print). If you see a stale `last_check`
timestamp, the integration is correctly deferring to the active print —
the next idle tick will refresh.

### Container can pair but can't print

You paired the printer from inside the HA container (using `bluetoothctl`
with `/run/dbus` mounted), but prints fail with `bt_unavailable`.

**Cause:** pairing went through D-Bus (which `/run/dbus` exposes), but
the actual data-plane RFCOMM open uses `AF_BLUETOOTH` directly, which
needs `network_mode: host` and `NET_ADMIN` / `NET_RAW` capabilities.

**Solution:** add the missing docker-compose settings (see README), or
use the `socat` host-bridge fallback to avoid the privilege grant entirely.

### Notifications routed to BT printer were intercepted

If you're concerned about over-the-air eavesdropping, see the README's
[Security considerations]. Bluetooth Classic SPP with no PIN or PIN
`0000` is unencrypted. **Don't route OTPs, 2FA codes, or other sensitive
content to a Bluetooth printer.**

### Useful host-side diagnostic commands

```bash
# Confirm the kernel sees the printer
bluetoothctl paired-devices

# Show pairing details + service records
bluetoothctl info AA:BB:CC:DD:EE:FF

# Live-watch BT events while reproducing the issue
sudo dmesg -w | grep -i bluetooth

# Show RFCOMM channels exposed by the printer
sudo rfcomm -a   # only useful if you've used `rfcomm bind`

# Test a manual RFCOMM connection without HA
sudo rfcomm connect 0 AA:BB:CC:DD:EE:FF 1
# (Ctrl-C to exit; if this connects, HA's adapter will too)
```

---

## Print Quality Problems

### Garbled or wrong characters

The codepage setting doesn't match your printer.

**Solutions:**

1. Try a different codepage in the integration options
2. Use the `print_text_utf8` service for text with special characters
3. Check your printer's documentation for supported codepages

**Common codepage choices:**

- CP437 - US English, good for basic ASCII
- CP850 - Western European languages
- CP1252 - Windows Western European

### Special characters not printing

Your text contains characters not supported by the printer's codepage.

**Solution:** Use `escpos_printer.print_text_utf8` instead of `print_text`. This
service automatically converts unsupported characters to their closest equivalents.

Characters like curly quotes, em-dashes, and accented letters will be converted:

- "smart quotes" become "straight quotes"
- em-dash becomes --
- accented letters are simplified when necessary

### Text is cut off or wrapping incorrectly

The line width setting doesn't match your printer.

**Solutions:**

1. Check your printer's documentation for characters per line
2. Adjust the Line Width setting in integration options
3. Common values: 32 (58mm paper), 42-48 (80mm paper)

### Print is too light or too dark

This is a hardware setting on the printer, not something the integration controls.

**Solutions:**

- Check your printer's settings menu for print density
- Some printers have DIP switches for density
- Thermal paper quality affects print darkness

---

## Service Errors

### "Service not found"

The integration isn't loaded properly.

**Solutions:**

1. Restart Home Assistant
2. Check **Settings** > **Devices & services** to verify the integration is loaded
3. Check the Home Assistant logs for errors during startup

### "No valid ESC/POS printer targets found"

You're using device targeting but no valid printer was found.

**Possible causes:**

- The device ID is incorrect
- The printer's config entry isn't loaded
- The entity/area doesn't belong to an ESC/POS printer

**Solutions:**

1. Verify the device ID in **Settings** > **Devices & services** > click your printer
2. Try omitting the `target` parameter to broadcast to all printers
3. Check that the printer is properly configured and online

### "Printer configuration not found"

The printer was removed or the integration was reloaded.

**Solutions:**

1. Restart Home Assistant
2. Remove and re-add the integration

### Timeout errors during printing

The printer is taking too long to respond.

**Solutions:**

1. Increase the timeout value in integration options
2. Check network connectivity
3. Reduce image size or complexity
4. The printer might be processing a large print job

---

## Image Issues

### "Image too large"

The image exceeds the maximum allowed size.

**Solutions:**

1. Resize the image to under 512 pixels wide
2. Use an image editor to reduce file size
3. Images are automatically resized, but very large files may be rejected

### Image doesn't print

**Common causes:**

- Unsupported image format
- Image URL not accessible from Home Assistant
- Local path doesn't exist

**Solutions:**

1. Use PNG or JPEG format
2. For URLs, verify the URL is accessible from the HA host
3. For local files, use absolute paths starting with `/config/`
4. Check that the file exists: **Developer Tools** > **Terminal** (if available)

### Image quality is poor

Thermal printers have limited resolution and only print in black and white.

**Tips:**

- Use simple graphics with high contrast
- Black and white images work better than grayscale
- Line art prints better than photos
- Keep images small - 200-300 pixels wide is often enough

### Image prints as solid black

The image is too dark or has no transparency handling.

**Solutions:**

- Use images with white backgrounds instead of transparent
- Increase contrast in the image
- Convert to 1-bit black and white before printing

---

## Paper and Cutting

### Paper doesn't cut

**Possible causes:**

- Printer doesn't have an auto-cutter
- Cutter is disabled in printer settings
- Paper type doesn't work with cutter

**Solutions:**

1. Verify your printer has a cutter (not all do)
2. Try `partial` cut instead of `full`
3. Check printer documentation for cutter settings

### Partial cut leaves too much paper attached

This is normal behavior for partial cut. If you need a cleaner cut, use
`full` cut mode.

### Paper jams during cutting

**Solutions:**

- Make sure you're using the correct paper width
- Check for paper debris in the cutter mechanism
- Some cheap paper doesn't cut well

---

## Multiple Printers

### Services go to wrong printer

When you have multiple printers, always use the `target` parameter to specify
which one.

**Example:**

```yaml
service: escpos_printer.print_text
target:
  device_id: correct_printer_id
data:
  text: "Hello"
```

### Broadcast not reaching all printers

Verify all printers are:

1. Properly configured in the integration
2. Online and reachable
3. Not in an error state

Check the binary sensor for each printer to see their status.

### Can't find device ID

1. Go to **Settings** > **Devices & services**
2. Click on "ESC/POS Thermal Printer"
3. Click on the printer
4. The device ID is in your browser's URL bar

---

## Debug Logging

Enable debug logging to get detailed information about what's happening.

### Enable Debug Logs

Add this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.escpos_printer: debug
    escpos: debug
```

Restart Home Assistant to apply.

### View Logs

Go to **Settings** > **System** > **Logs**

Or use the command line:

```bash
# For Home Assistant OS
ha core logs | grep escpos

# For Docker
docker logs homeassistant 2>&1 | grep escpos
```

### What to look for

- Connection errors show network issues
- "Service call" messages show what's being sent to the printer
- "Transcoded text" messages show UTF-8 conversion details
- Exception tracebacks show the exact error

---

## Printer-Specific Issues

### Epson TM Series

**ESC/POS mode:** Make sure the printer is in ESC/POS mode, not Epson
proprietary mode. Check DIP switch settings.

**Network config:** Print a network status page by holding the feed button
during power-on.

### Star Micronics

**Emulation mode:** Verify the printer is set to ESC/POS emulation, not Star
native mode.

**Interface settings:** Check the printer's web interface (if available) for
network settings.

### Generic/Unbranded Printers

**Start simple:** Use the "Auto-detect" profile and basic print_text calls first.

**Codepage:** Try CP437 first, then CP850 if you need European characters.

**Features:** Some cheap printers don't support all ESC/POS commands. If a
feature doesn't work (like QR codes), the printer may not support it.

---

## Getting More Help

If you've tried these solutions and still have issues:

1. **Enable debug logging** and capture relevant log entries
2. **Check existing issues** on [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues)
3. **Create a new issue** with:
   - Your printer model
   - Home Assistant version
   - Integration version
   - Debug log output
   - Steps to reproduce the problem
