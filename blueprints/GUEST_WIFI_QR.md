# Guest Wi-Fi QR — setup guide

The [Guest Wi-Fi QR](script/escpos_printer/guest_wifi_qr.yaml) blueprint prints a scannable QR code that lets a guest join your Wi-Fi with one tap (and prints the SSID + password in plain text as a fallback for devices without a QR scanner). This guide covers three ways to set it up, ordered by complexity. For the format spec and limitations, see [Format & limitations](#format--limitations) at the bottom.

**Inputs:** printer · `ssid` · `password` · `security` (WPA / WEP / nopass) · `hidden` · `title` · `qr_size` · `show_password`

## Quick start (works on any router — about 2 minutes)

You do not need a UniFi controller, an API, or any extra integrations. This is the path 90% of users want:

1. Click the **Import** badge for "Guest Wi-Fi QR" in [the catalogue](README.md#available-blueprints). HA opens the blueprint import dialog with the URL pre-filled — confirm.
2. Go to **Settings → Automations & Scenes → Scripts**. Click **+ Add Script** → **Create script from blueprint** → pick **ESC/POS — Guest Wi-Fi QR**.
3. Fill in:
   - **Printer**: your ESC/POS device
   - **SSID**: your guest network name (typed literally, e.g. `MyHouse-Guest`)
   - **Password**: the Wi-Fi password (typed literally)
   - **Security**: usually `WPA` (covers WPA2 / WPA3 on modern phones)
   - Leave the rest at defaults
4. **Save**. The script appears as `script.escpos_guest_wifi_qr` (or whatever you named it).
5. Test: **Settings → Automations & Scenes → Scripts**, find your script, click **Run**. A slip with the QR + credentials prints. Scan it with your phone — you should get a "Join network" prompt.
6. Add a Lovelace button:

   ```yaml
   type: button
   name: Guest Wi-Fi
   icon: mdi:wifi
   tap_action:
     action: perform-action
     perform_action: script.escpos_guest_wifi_qr   # your script's entity_id
   ```

That's it. When you change the Wi-Fi password (or guests turn over and you want to rotate), just edit the script's inputs and save.

## A bit nicer: store credentials in helpers

If you don't want to edit the script every time the password changes:

1. **Settings → Devices & Services → Helpers → + Create Helper → Text** — name it `Guest Wi-Fi SSID` (`input_text.guest_wifi_ssid` by default).
2. Repeat for **Guest Wi-Fi Password**, setting **Mode: Password** so it masks in the UI (`input_text.guest_wifi_password`).
3. Fill in the values once.
4. Edit your blueprint-based script (**Scripts → your guest wi-fi script → ⚙ Edit in YAML** or via the UI) and change the SSID and password inputs to:

   ```yaml
   ssid: "{{ states('input_text.guest_wifi_ssid') }}"
   password: "{{ states('input_text.guest_wifi_password') }}"
   ```

5. Save. Now you update the password by editing the helper, not the script. Useful when:
   - You let a non-technical household member rotate the password from a Lovelace text field.
   - You want the same value in multiple automations / templates.
   - You plan to automate rotation later (see below).

## Automating rotation

If you have the [official HA UniFi integration](https://www.home-assistant.io/integrations/unifi/) installed, you can rotate the guest password on a schedule and reprint anytime: see [**UNIFI_GUEST_WIFI.md**](UNIFI_GUEST_WIFI.md) (~10 minutes of setup, one shell script, reuses the UniFi integration's stored credentials).

For other routers (OpenWrt, Mikrotik, etc.), the same shape works — replace the UniFi `curl` calls in `unifi_wifi.sh` with your router's API equivalent. For routers without an API (most ISP modems), rotate manually in the router UI, update your input_text helpers, and tap print.

## Format & limitations

**Encoded format:** the ZXing "WIFI" URI scheme — `WIFI:T:<auth>;S:<ssid>;P:<password>;H:<hidden>;;`. Reserved characters (`\`, `;`, `,`, `:`, `"`) are backslash-escaped per spec. There is no IETF RFC or IEEE standard for this format, but every consumer QR scanner implements ZXing's: iOS Camera (15+), Google Camera, Android system scanner, Windows Camera, macOS Continuity Camera. Canonical reference: [ZXing Barcode Contents — Wi-Fi Network Config](https://github.com/zxing/zxing/wiki/Barcode-Contents#wi-fi-network-config-android-ios-11).

**Auth types supported:** `WPA` (covers WPA2 + WPA3 on iOS 17+ / modern Android — the radio negotiates the actual mode), `WEP` (legacy), `nopass` (open networks). **Not supported by this blueprint:** WPA2-Enterprise (EAP) and explicit WPA3-Personal (SAE) tags. EAP needs additional `E:`, `PH:`, `A:`, `I:` fields; SAE is `T:SAE` but most devices auto-negotiate from `T:WPA`. If you specifically need either, fork the blueprint and extend the `wifi_uri` template.

`show_password: false` prints just the QR for a more secure share — anyone seeing the slip can only join by scanning.
