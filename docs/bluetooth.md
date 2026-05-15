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

HA Container needs `network_mode: host`, `cap_add: [NET_ADMIN, NET_RAW]`, and a `/run/dbus` bind-mount to use BT printers. If you want to keep Docker isolation, prefer the `socat` host-bridge fallback documented in the [README](../README.md) — it routes BT prints through the existing Network adapter and needs no special container privileges.

## Battery sensor

For BT printers that expose `org.bluez.Battery1`, a `sensor.<printer>_battery` entity is created reporting % charge. Most cheap thermal printers don't expose this and the sensor stays unavailable; portable models (Phomemo M02, newer Netum firmware, some Cashino models) do.

## Security considerations

Bluetooth Classic SPP / RFCOMM is **plaintext by default** with no-PIN or `0000` pairings. **Don't route OTPs, 2FA codes, or other sensitive content to a Bluetooth printer**. See the [README's security section](../README.md#security-considerations) for the threat model.

The integration enforces a recommended `status_interval` floor of 60 seconds for BT entries — aggressive polling makes cheap printers beep on every probe and competes with in-flight prints.

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
