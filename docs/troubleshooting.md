# Troubleshooting

For known limitations, see [limitations.md](limitations.md).

## Network issues

### "Cannot connect to printer"

```bash
ping <PRINTER_IP>
telnet <PRINTER_IP> 9100   # blank screen = reachable; Ctrl+] then `quit` to exit
```

Common causes:
- Wrong IP (print a network status page from the printer itself)
- Printer in sleep mode
- Firewall blocking port 9100
- Printer on a different subnet

Fixes: increase the timeout (try 8–10s), assign a static IP, verify port 9100.

### Connection works sometimes

DHCP lease churn or sleep mode. Assign a static IP, disable sleep, optionally enable Keep Alive.

### "Connection refused"

Another app is using the printer, or it's in an error state (paper out, cover open). Power-cycle.

## USB issues

### "Permission denied" / "Access denied"

On bare Linux, add a udev rule:

```bash
# /etc/udev/rules.d/99-escpos.rules
SUBSYSTEM=="usb", ATTR{idVendor}=="04b8", MODE="0666"
```

Replace `04b8` with your vendor ID. Reload:

```bash
sudo udevadm control --reload-rules
sudo udevadm trigger
```

In Docker: pass the device through (`/dev/bus/usb:/dev/bus/usb`).

### "Device not found"

```bash
lsusb | grep -i printer
```

Try a different cable / port. Verify the printer is powered on.

### "Input/Output Error" (errno 5)

libusb's generic I/O error — usually USB autosuspend or another driver holds the device.

Fixes:
- Replug the printer.
- Disable USB autosuspend:
  ```bash
  echo -1 > /sys/bus/usb/devices/usb*/power/autosuspend
  ```
- Stop other apps holding the device (CUPS, lp drivers).

### "USB backend missing"

libusb not installed. HA OS includes it. On bare Linux: `sudo apt install libusb-1.0-0`. In Docker: ensure libusb is in your image.

### Wrong endpoints

```bash
lsusb -v -d VENDOR:PRODUCT | grep Endpoint
```

Look for `bEndpointAddress`. Defaults are `0x82` (in) and `0x01` (out).

### Printer not auto-discovered

Vendor ID isn't in the known list. Use **Browse all USB devices** or **Manual entry** with VID:PID.

## Bluetooth issues

### Error key reference

| Error key | Likely cause | Action |
|-----------|--------------|--------|
| `bt_unavailable` | Kernel `AF_BLUETOOTH` not reachable (HA Container without `--net=host`) | Add `network_mode: host` to compose; or use `socat` host-bridge fallback |
| `bt_permission_denied` | HA process can't open BT socket | Add HA user to `bluetooth` group on bare Linux |
| `bt_device_not_found` | Printer never paired, or pairing was removed | Pair on host first (see [bluetooth.md](bluetooth.md#one-time-pairing)) |
| `bt_host_down` | Powered off, out of range, already connected to another host | Power on, bring closer, disconnect other host |
| `bt_timeout` | Printer asleep — first probe missed | Print once to wake, or increase timeout |
| `bt_channel_refused` | Wrong RFCOMM channel | Use 1; confirm via `bluetoothctl info <MAC>` |
| `cannot_connect_bt` | Catchall (errno not recognized) | Check HA debug logs |
| `invalid_bt_mac` | MAC format invalid | Use `AA:BB:CC:DD:EE:FF` (uppercase, colons) |
| `invalid_rfcomm_channel` | Channel out of range | Must be 1–30 (almost always 1) |

### "Bluetooth not available"

Kernel `AF_BLUETOOTH` socket family isn't reachable from the HA process.

- HA Container without `--net=host` — add to compose.
- Rootless Docker / Podman — bluez D-Bus EXTERNAL auth fails across UID namespaces. Use the `socat` host-bridge fallback.
- Non-Linux host — `AF_BLUETOOTH` is Linux-only. Use a network printer or the `socat` bridge.

### Status flaps online/offline

Most BT thermal printers sleep aggressively. Each RFCOMM connect takes 1–3s. Set **Status check interval** to 60s+ (or 0). Verify pairing is intact:

```bash
bluetoothctl info AA:BB:CC:DD:EE:FF
# Look for "Paired: yes" and "Trusted: yes"
```

If the printer was factory-reset or its battery fully drained, the link key may be invalid. Re-pair:

```bash
bluetoothctl
[bluetooth]# remove AA:BB:CC:DD:EE:FF
[bluetooth]# pair AA:BB:CC:DD:EE:FF
[bluetooth]# trust AA:BB:CC:DD:EE:FF
```

### Paired-device list empty in config flow

D-Bus not reachable, or printer simply not paired:

```bash
bluetoothctl paired-devices  # on the host
```

If your printer shows there but not in HA, the HA process can't reach the system D-Bus. On HA Container, add `/run/dbus:/run/dbus:ro` to volume mounts.

### Useful host-side commands

```bash
bluetoothctl paired-devices         # confirm pairing
bluetoothctl info AA:BB:CC:DD:EE:FF # show service records (channel)
sudo dmesg -w | grep -i bluetooth   # live BT events
sudo rfcomm connect 0 AA:BB:CC:DD:EE:FF 1  # manual RFCOMM probe
```

## Print-quality problems

- **Garbled characters** — codepage mismatch. Try CP437, CP850, or use `print_text_utf8`.
- **Special characters missing** — printer codepage doesn't support them. Use `print_text_utf8` for best-effort transliteration.
- **Text wraps wrong** — line width setting wrong. 32 for 58mm paper, 42–48 for 80mm.
- **Print too light/dark** — printer hardware setting. Not controllable from the integration.

## Service errors

- **"Service not found"** — restart HA; verify the integration loaded.
- **"No valid ESC/POS printer targets found"** — wrong device ID, or entry not loaded. Omit `target:` to broadcast.
- **"Printer configuration not found"** — entry was removed. Restart HA or re-add.
- **Timeout errors during printing** — increase timeout, reduce image size, check network.

## Image issues

- **"Image too large"** — resize under 512px wide.
- **Image doesn't print** — use PNG or JPEG; for URLs verify reachable from HA host; for local files use absolute paths starting with `/config/`.
- **Image prints solid black** — image is too dark or has alpha issues. Use white background, increase contrast, convert to 1-bit B&W.

## Paper and cutting

- **Paper doesn't cut** — verify the printer has an auto-cutter. Try `partial` instead of `full`.
- **Partial cut leaves too much attached** — normal; use `full` if you need a cleaner cut.
- **Paper jams during cutting** — wrong paper width, debris in cutter, or low-grade paper.

## Debug logging

Add to `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.escpos_printer: debug
    escpos: debug
```

Restart HA. View at **Settings → System → Logs**, or:

```bash
ha core logs | grep escpos             # HA OS
docker logs homeassistant 2>&1 | grep escpos  # Docker
```

## Printer-specific notes

- **Epson TM series** — verify ESC/POS mode (not Epson proprietary). Check DIP switches.
- **Star Micronics** — verify ESC/POS emulation (not Star native mode). Check the printer's web interface.
- **Generic / unbranded** — use **Auto-detect** profile. Try CP437 first. Some cheap printers don't support all ESC/POS commands (QR codes, beep, cut).

## Getting more help

1. Enable debug logging.
2. Check [GitHub Issues](https://github.com/cognitivegears/ha-escpos-thermal-printer/issues).
3. Open a new issue with: printer model, HA version, integration version, debug log, repro steps.
