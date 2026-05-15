# Bluetooth (RFCOMM) Printers

For portable, battery-powered ESC/POS printers (Netum, MUNBYN, POS-58 generics, Phomemo Classic line).

> **Important:** Home Assistant's built-in Bluetooth integration scans for and discovers devices, but it does **not** pair Classic Bluetooth devices like thermal printers. You must pair the printer manually at the operating system level **before** adding it in HA. The integration never initiates pairing itself.

## Requirements

- A Linux host with the kernel `AF_BLUETOOTH` socket family. Any HA OS, Supervised, Core, or Container with `--net=host` works.
- A working Bluetooth adapter on the host.
- The printer **paired on the host** before adding it in HA (see below).
- For the paired-device picker in the config flow, read access to the system D-Bus (`/run/dbus`). Without it, the flow falls back to manual MAC entry.

## Pairing walkthrough (HA OS / Supervised)

This is the most common setup. You'll need terminal access to the HA host.

### Before you start: install a terminal add-on

If you don't already have a way to run shell commands on the HA host, install the **Advanced SSH & Web Terminal** add-on:

1. Go to **Settings → Add-ons → Add-on Store**
2. Search for **Advanced SSH & Web Terminal** (by Frenck)
3. Install, configure a password or SSH key, then **Start** it
4. Open the terminal from the add-on's web UI, or SSH in from your computer

> The official **Terminal & SSH** add-on also works. The "Advanced" version is recommended because it runs in the host context where `bluetoothctl` is available.

Power on your printer and put it within ~10 metres of the HA host. Some printers need to be put into pairing mode first — usually by holding the power button until an LED blinks rapidly. Check your printer's manual.

### Step 1 — Check whether the printer is already visible

HA's Bluetooth integration usually scans in the background, so your printer may already be known to BlueZ. In the terminal, run:

```bash
bluetoothctl devices
```

You'll see a list like:

```
Device DC:0D:51:5F:43:3E MPT-II
Device 4C:24:98:1A:2B:3C PeriPage_A1
```

If your printer is in the list, **skip to Step 3**. If the list is long, filter it by part of the name:

```bash
bluetoothctl devices | grep -i mpt
```

### Step 2 — Scan manually (only if the printer wasn't listed)

```bash
bluetoothctl scan on
```

Wait 10–15 seconds, then stop the scan and re-list:

```bash
bluetoothctl scan off
bluetoothctl devices
```

The printer should now appear. Note the MAC address (the `XX:XX:XX:XX:XX:XX` value).

### Step 3 — Pair and trust

Replace `XX:XX:XX:XX:XX:XX` with your printer's MAC address:

```bash
bluetoothctl pair XX:XX:XX:XX:XX:XX
bluetoothctl trust XX:XX:XX:XX:XX:XX
```

You should see `Pairing successful` and `Trusted: yes`. **`trust` is what tells BlueZ to auto-reconnect after a reboot — don't skip it.**

If you're prompted for a PIN, try `0000` or `1234` — these are the most common defaults for cheap thermal printers.

### Step 4 — Verify

```bash
bluetoothctl devices Paired
```

The printer should be in this list. You can also check `bluetoothctl devices Trusted` and `bluetoothctl devices Connected`.

### Step 5 — Add the integration in HA

1. Go to **Settings → Devices & Services**
2. Click **Add Integration** and search for **ESC/POS Thermal Printer**
3. Choose **Bluetooth (RFCOMM)** as the connection type
4. Pick your printer from the paired-device list (or use **Manual MAC entry** if it doesn't show up)
5. Accept the defaults and finish

> If HA shows "No paired Bluetooth printers found" right after pairing, restart Home Assistant (**Settings → System → Restart**) and try again.

The dropdown filters to imaging-class Bluetooth devices by default so your phone and headset don't clutter the list. If your printer doesn't advertise the Class-of-Device correctly (some cheap models don't), pick **Show all paired Bluetooth devices** from the dropdown. Or use **Manual MAC entry** if you already know the address.

The **RFCOMM channel** is hidden by default — almost every ESC/POS printer uses channel 1. If the connection test fails with `bt_channel_refused` you'll be prompted for a different one. Power users can also enable HA's *Advanced Mode* in their profile to surface the field up-front.

### No paired devices found

If the picker shows **No paired Bluetooth printers found**:

- The host can't see any paired BT devices, *or*
- bluez D-Bus isn't reachable from the HA process (most likely on HA Container without `/run/dbus` mounted, or rootless Docker).

Pair the printer first using the steps above, or — if you already know the MAC — submit the form to enter it manually. The data plane works without bluez D-Bus as long as `AF_BLUETOOTH` is reachable.

## Connection settings

| Setting | Description | Default |
|---------|-------------|---------|
| Bluetooth device | Picked from paired devices, or **Manual MAC entry** | Required |
| MAC address | `AA:BB:CC:DD:EE:FF` (manual entry only) | Required |
| RFCOMM channel | Service channel — 1 for almost every ESC/POS printer | 1 |
| Timeout | Connect timeout (seconds) | 4.0 |
| Printer Profile | Your printer model | Auto-detect |

## Confirming the RFCOMM channel

Almost every ESC/POS printer exposes SPP on **channel 1**. If you get `bt_channel_refused`, look up the printer's SDP records:

```bash
bluetoothctl info AA:BB:CC:DD:EE:FF
# Look for the SerialPort service-record entry — its "Channel:" line is
# the value to use.
```

## Container deployments

HA Container needs the host's Bluetooth stack exposed for the BT printer flow:

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

These settings substantially weaken Docker's isolation — see [Security considerations](#security-considerations) before adopting them. **If you care about container isolation, use the [`socat` host bridge](#host-bridge-fallback-socat) instead.**

**Rootless Docker / Podman** is not supported because of a known D-Bus EXTERNAL-auth limitation; use the host bridge.

## Host bridge fallback (`socat`)

If exposing bluez D-Bus to your container isn't workable, run `socat` on the host as a one-line bridge and use the integration's existing **Network (TCP/IP)** flow instead — zero new code path, no privilege grants:

```bash
# Install socat once: apt install socat
socat TCP-LISTEN:9100,reuseaddr,fork BLUETOOTH-RFCOMM:AA:BB:CC:DD:EE:FF:1 &
```

Add the printer in HA as a network printer at `127.0.0.1:9100`.

## Battery sensor

For BT printers that expose `org.bluez.Battery1`, a `sensor.<printer>_battery` entity is created reporting % charge. Most cheap thermal printers don't expose this and the sensor stays unavailable; portable models (Phomemo M02, newer Netum firmware, some Cashino models) do.

## Security considerations

Bluetooth Classic / RFCOMM has security properties you should understand before routing sensitive notifications to a paired printer:

- **The radio link is not encrypted by default.** Most ESC/POS thermal printers pair with no PIN or with `0000`, both of which negotiate a "Just Works" link key. ESC/POS bytes are recoverable over the air with consumer-grade SDR / Ubertooth equipment within ~10 metres. **Avoid routing OTPs, 2FA codes, door-access logs, alarm-disarm codes, or other sensitive content to a Bluetooth printer.**
- **Pairing is not authentication.** An attacker who can spoof your printer's MAC (`bdaddr -i hci0 AA:BB:CC:DD:EE:FF`) and listen on RFCOMM channel 1 will receive every print HA sends while the real printer is off or out of range. If integrity matters, prefer wired (USB) or a network printer on a trusted VLAN. Re-pair after any factory reset, theft, or extended absence.
- **Container exposure trade-off.** The docker-compose settings in [Container deployments](#container-deployments) remove Docker's network-namespace isolation, grant raw-socket / iptables / route-table powers, and expose the system D-Bus protocol (`:ro` only protects the socket *file*, not bus messages). A vulnerability in any HA integration becomes more impactful in this configuration. Prefer the [`socat` host bridge](#host-bridge-fallback-socat) when isolation matters.
- **Status polling competes with prints.** Bluetooth Classic accepts one client at a time, so each status check is a real RFCOMM open and many cheap printers audibly beep on every connect. Set **Status check interval** to **60 seconds or longer** (or leave at `0` and rely on print success/failure for liveness). Aggressive polling beeps the printer, drains battery on portable models, and contends with in-flight print jobs. The integration enforces a recommended floor of 60 seconds for BT entries.

## Troubleshooting

### Pairing problems

- **Printer doesn't appear in `bluetoothctl devices` even after scanning** — Power-cycle the printer, make sure it's in pairing mode (often signalled by a fast-blinking LED), and confirm it's within ~10 m of the HA host. Some printers stop advertising after a minute or two.
- **`bluetoothctl pair` fails or times out** — Try again with the printer freshly powered on. If prompted for a PIN, try `0000` or `1234`. Some printers need to be removed first: `bluetoothctl remove XX:XX:XX:XX:XX:XX`, then re-pair.
- **Printer disappears after rebooting HA** — You skipped `bluetoothctl trust`. Run it now; trusting is what tells BlueZ to auto-reconnect.
- **`bluetoothctl` command not found** — You're probably in the standard **Terminal & SSH** add-on which runs in a restricted container. Switch to the **Advanced SSH & Web Terminal** add-on, which runs in the host context.

### HA-side problems

- **"No paired Bluetooth printers found" in the config flow** — Restart Home Assistant after pairing (**Settings → System → Restart**). If it still doesn't appear, use **Manual MAC entry** with the address from `bluetoothctl devices`.
- **`bt_unavailable`** — Kernel doesn't expose `AF_BLUETOOTH`. HA Container without `--net=host` is the typical culprit.
- **`bt_permission_denied`** — HA process lacks Bluetooth socket permission. Add to the `bluetooth` group on bare Linux.
- **`bt_device_not_found`** — Printer was never paired on the host, or pairing didn't persist. Re-run Steps 3–4.
- **`bt_host_down`** — Printer powered off, out of range, or already connected to another host (phones in particular like to grab BT printers).
- **`bt_channel_refused`** — Wrong RFCOMM channel; almost always means use 1. See "Confirming the RFCOMM channel" above.
- **Paired-device list empty in the flow** — D-Bus not reachable; the flow falls through to manual MAC entry.

See [troubleshooting.md](troubleshooting.md#bluetooth-issues) for the full error-key reference.
