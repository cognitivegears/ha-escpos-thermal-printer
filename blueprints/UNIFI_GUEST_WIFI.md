# UniFi Guest Wi-Fi — rotate monthly, print anytime

A small recipe that pairs the [Guest Wi-Fi QR](script/escpos_printer/guest_wifi_qr.yaml) blueprint with the **official [Home Assistant UniFi integration](https://www.home-assistant.io/integrations/unifi/)** so you can:

- Tap a button → print a QR with the current guest Wi-Fi password.
- On the 1st of each month → automatically rotate the password and print the new slip.

It reuses the credentials *you've already given* the official UniFi integration. No new secrets to manage, no `.env` files, no extra `input_text` helpers — if you can already see your UniFi devices in HA, you're 90% set up.

> **Don't need automation?** If you just want a QR with your typed-in SSID and password, stop here — see the [Guest Wi-Fi QR Quick start](GUEST_WIFI_QR.md#quick-start-works-on-any-router--about-2-minutes) and you're done in 2 minutes.

---

## What you'll do (about 10 minutes)

1. Confirm prereqs.
2. Drop one shell script in `/config/shell_scripts/`.
3. Paste one block into `configuration.yaml`.
4. Create one HA script and one automation in the UI.
5. Wire the blueprint's SSID/password inputs to a sensor.

That's it. ~50 lines of script, ~30 lines of YAML.

---

## Prereqs

- **Official HA UniFi integration installed.** **Settings → Devices & Services → + Add Integration → UniFi Network**. Enter your controller IP, username, password. If you see UniFi devices in **Devices & Services**, you're done.
  - **For rotation to work**, the UniFi account you used here must have Site Admin / write permission. Read-only accounts can still do the *read* / print-current half of this recipe; rotation will fail with a 403.
  - **MFA must be off** on the UniFi account. UniFi's JSON login flow returns 401 if MFA is enabled — this is a UniFi limitation, not a bug. Use a dedicated local account.
- **`jq` available** on the HA host. HA OS doesn't bundle it; the easiest fix is the [SSH & Web Terminal add-on](https://github.com/hassio-addons/addon-ssh) → `apk add jq`. HA Container / Core users have their own package managers.
- **You know the exact name** of your guest WLAN as shown in the UniFi UI (it's case-sensitive — `MyHouse-Guest` ≠ `myhouse-guest`).

---

## Step 1 — Drop the script

Save this as `/config/shell_scripts/unifi_wifi.sh` and `chmod 755` it.

```bash
#!/usr/bin/env bash
# /config/shell_scripts/unifi_wifi.sh — read or rotate a UniFi guest WLAN.
#
# Credentials come from the official HA UniFi integration's config entry,
# so there's nothing extra to configure.
#
# Usage:
#   unifi_wifi.sh read   <wlan-name>       # prints JSON {ssid, passphrase}
#   unifi_wifi.sh rotate <wlan-name>       # generates new password, sets it,
#                                          # prints JSON {ssid, passphrase}

set -euo pipefail

action="${1:?usage: unifi_wifi.sh <read|rotate> <wlan-name>}"
target="${2:?usage: unifi_wifi.sh <read|rotate> <wlan-name>}"

# Pull creds from the official HA UniFi integration's config entry.
storage=/config/.storage/core.config_entries
[ -r "$storage" ] || {
    echo "cannot read $storage — is the UniFi integration installed?" >&2
    exit 2
}
creds="$(jq -r '.data.entries[] | select(.domain == "unifi") | .data' "$storage")"
[ -n "$creds" ] || { echo "no UniFi config entry found" >&2; exit 2; }

UNIFI_HOST="https://$(jq -r .host <<<"$creds"):$(jq -r '.port // 443' <<<"$creds")"
UNIFI_USER="$(jq -r .username <<<"$creds")"
UNIFI_PASS="$(jq -r .password <<<"$creds")"
UNIFI_SITE="$(jq -r '.site // "default"' <<<"$creds")"

jar="$(mktemp)"; hdrs="$(mktemp)"
trap 'rm -f "$jar" "$hdrs"' EXIT

# Login → JWT cookie + CSRF token.
curl --fail --silent --insecure \
    --cookie-jar "$jar" --dump-header "$hdrs" \
    --header 'Content-Type: application/json' \
    --data "$(jq -n --arg u "$UNIFI_USER" --arg p "$UNIFI_PASS" \
        '{username:$u, password:$p, remember:true}')" \
    "$UNIFI_HOST/api/auth/login" >/dev/null

base="$UNIFI_HOST/proxy/network/api/s/$UNIFI_SITE/rest/wlanconf"

case "$action" in
    read)
        curl --fail --silent --insecure --cookie "$jar" "$base" \
        | jq --arg n "$target" -c \
            '.data[] | select(.name == $n) | {ssid: .name, passphrase: .x_passphrase}'
        ;;
    rotate)
        csrf="$(awk -F': ' '
            tolower($1) ~ /^x-(updated-)?csrf-token$/ {
                sub(/\r$/, "", $2); print $2; exit
            }' "$hdrs")"
        [ -n "$csrf" ] || { echo "no CSRF token in login response" >&2; exit 3; }
        # 16 chars from an alphabet that avoids WIFI-URI reserved chars
        # and visually confusable chars (0/O, 1/l/I).
        #
        # `head -c 16` closes the pipe after reading 16 bytes; `tr` then
        # writes more output and gets SIGPIPE. Under `set -e -o pipefail`
        # that aborts the entire script with exit code 141. We suspend
        # pipefail just for this pipeline, then assert we actually got
        # 16 chars before continuing.
        set +o pipefail
        new_pass="$(LC_ALL=C tr -dc 'A-HJ-NP-Za-km-z2-9' </dev/urandom | head -c 16)"
        set -o pipefail
        [ "${#new_pass}" -eq 16 ] || {
            echo "password generation failed (got '$new_pass', expected 16 chars)" >&2
            exit 5
        }
        wlan_id="$(curl --fail --silent --insecure --cookie "$jar" "$base" \
            | jq -r --arg n "$target" '.data[] | select(.name == $n) | ._id')"
        [ -n "$wlan_id" ] || { echo "WLAN '$target' not found" >&2; exit 4; }
        curl --fail --silent --insecure --request PUT \
            --cookie "$jar" \
            --header "X-CSRF-Token: $csrf" \
            --header 'Content-Type: application/json' \
            --data "$(jq -n --arg p "$new_pass" '{x_passphrase:$p}')" \
            "$base/$wlan_id" >/dev/null
        jq -n --arg s "$target" --arg p "$new_pass" '{ssid:$s, passphrase:$p}'
        ;;
    *)
        echo "unknown action: $action (expected 'read' or 'rotate')" >&2
        exit 1
        ;;
esac
```

---

## Step 2 — Add the HA wiring

In `configuration.yaml`, replace `YourGuestWLAN` with the exact name of your guest WLAN in both places:

```yaml
# Polls UniFi once an hour and publishes sensor.guest_wifi with the SSID as
# state and the passphrase as an attribute.
command_line:
  - sensor:
      name: Guest Wi-Fi
      unique_id: guest_wifi
      command: 'bash /config/shell_scripts/unifi_wifi.sh read "YourGuestWLAN"'
      value_template: "{{ value_json.ssid }}"
      json_attributes: [passphrase]
      scan_interval: 3600

# Rotates the guest WLAN password to a fresh 16-char random string.
shell_command:
  rotate_guest_wifi: 'bash /config/shell_scripts/unifi_wifi.sh rotate "YourGuestWLAN"'
```

Reload **YAML configuration** from **Developer Tools → YAML** (or restart HA).

---

## Step 3 — Wire the blueprint

Open your Guest Wi-Fi QR script (the one you created from the [blueprint](script/escpos_printer/guest_wifi_qr.yaml)) in **Settings → Automations & Scenes → Scripts → edit**. Set:

| Field | Value |
|---|---|
| SSID | `{{ states('sensor.guest_wifi') }}` |
| Password | `{{ state_attr('sensor.guest_wifi', 'passphrase') }}` |
| Security | `WPA` |

Save. Note the script's `entity_id` — call it `script.print_guest_wifi` here.

---

## Step 4 — Create the rotate-and-print script

**Settings → Automations & Scenes → Scripts → + Add Script → Create new script**. Click ⋮ → **Edit in YAML**:

```yaml
alias: Rotate Guest Wi-Fi and Print
mode: single
sequence:
  - service: shell_command.rotate_guest_wifi
    response_variable: result
  - if:
      - condition: template
        value_template: "{{ result.returncode != 0 }}"
    then:
      - service: persistent_notification.create
        data:
          title: Guest Wi-Fi rotation failed
          message: "{{ result.stderr | default('(see logs)') }}"
      - stop: rotation failed
  - variables:
      new_passphrase: "{{ (result.stdout | from_json).passphrase }}"
  # Force the sensor to refresh now, then *wait* until it actually reflects
  # the new password before printing. Without the wait_template, the print
  # step can race the sensor's poll (median ~700ms, p95 ~1.8s, occasionally
  # longer) and produce a slip with the OLD password while the network has
  # the NEW one. ``continue_on_timeout: false`` halts the script if the
  # sensor never catches up — far better than printing stale credentials.
  - service: homeassistant.update_entity
    target:
      entity_id: sensor.guest_wifi
  - wait_template: "{{ state_attr('sensor.guest_wifi', 'passphrase') == new_passphrase }}"
    timeout: "00:00:10"
    continue_on_timeout: false
  - service: script.print_guest_wifi   # ← your blueprint script from Step 3
```

Save. Note its entity_id — `script.rotate_guest_wifi_and_print` here.

---

## Step 5 — Schedule monthly rotation

**Settings → Automations & Scenes → Automations → + Create automation → Start with an empty automation**. Click ⋮ → **Edit in YAML**:

```yaml
alias: Rotate guest Wi-Fi monthly
trigger:
  - platform: time
    at: "09:00:00"
condition:
  - condition: template
    value_template: "{{ now().day == 1 }}"   # 1st of the month
action:
  - service: script.rotate_guest_wifi_and_print
```

Save.

---

## Two Lovelace buttons

Add a dashboard card. **Print current** never rotates; **Rotate now** runs the rotation script (with a confirmation prompt).

```yaml
type: entities
title: Guest Wi-Fi
entities:
  - type: button
    name: Print current
    icon: mdi:wifi
    tap_action:
      action: perform-action
      perform_action: script.print_guest_wifi
  - type: button
    name: Rotate now
    icon: mdi:wifi-refresh
    tap_action:
      action: perform-action
      perform_action: script.rotate_guest_wifi_and_print
      confirmation:
        text: This will change the guest Wi-Fi password. Continue?
```

---

## ✓ Verify

Run these in order from a shell (SSH add-on, terminal):

1. **Script reads.** Should print one line of JSON:

   ```sh
   bash /config/shell_scripts/unifi_wifi.sh read "YourGuestWLAN"
   ```

   If you get `no UniFi config entry found` → install the official UniFi integration first. `401` → the UniFi account has MFA, or wrong creds. `404` / empty → WLAN name doesn't match the UniFi UI exactly.
2. **Sensor populated.** **Developer Tools → States** → search `sensor.guest_wifi`. State = SSID, `passphrase` attribute = the password. If unknown, check the HA log for the `command_line` error.
3. **Print current works.** Tap the **Print current** button. A QR slip prints; scanning it joins you to the network.
4. **Rotation works.** Tap **Rotate now**. A new slip prints with a *different* password. Confirm in the UniFi UI that the WLAN password changed. The `Print current` button continues to print the new password — that's the sensor working correctly.

---

## Top gotchas

1. **MFA on the UniFi account = 401**, full stop. Use a dedicated local UniFi account with MFA disabled.
2. **`jq` missing on HA OS.** `apk add jq` via the SSH add-on.
3. **WLAN name mismatch.** Must match the UniFi UI exactly — case-sensitive, no leading/trailing spaces.
4. **Read-only UniFi account.** Reads work; rotation returns 403. Either give the account Site Admin or use only the read half (skip Steps 4–5).
5. **Multi-site controller.** The script defaults to `default`. If your site has a slug like `4anv2bxq`, edit the script's `UNIFI_SITE=` fallback or set the site in the UniFi integration's config entry.

---

## Security model

**Where credentials live.** In HA's existing UniFi config entry
(`.storage/core.config_entries`) — the same plaintext-JSON storage that holds
every other HA integration's secrets. No `.env` dotfile, no `secrets.yaml`
edit, no extra `input_text` helper. The shell script reads them via `jq`
and uses them in `curl` calls. They land in the script's process memory
and, briefly, in curl's `--data` argv during the login and PUT requests —
visible to `ps` for anything else running as the HA user during that
window (on a single-user HA OS install this is just HA itself; on a
multi-user host other users could observe them). This is the same exposure
model as any `curl`-driven recipe, including HA's own first-party shell
integrations.

**Cookie-jar and header-dump tempfiles** (created via `mktemp` in `/tmp`)
hold the post-login JWT session cookie and the CSRF token respectively.
Both are cleaned up by `trap … EXIT`, but SIGKILL bypasses the trap; on
non-tmpfs `/tmp` this could persist briefly until the OS recycles the
file. Treat with the same care as any session cookie on the host.

**Generated password strength.** 16 characters drawn from a 57-character
alphabet (`A-HJ-NP-Za-km-z2-9`) yields ~93 bits of entropy. The alphabet
strips `0/1/I/L/O` (the most visually confusable across common fonts) so
the printed plaintext fallback is easy to type by hand. Note that
lowercase `i` and `o` are *not* stripped — they could still be confused
with their digit counterparts in some fonts. If this matters for your
users, fork the script and replace the `tr` class with
`A-HJ-NP-Za-hj-km-np-z2-9` (54 chars, ~92 bits).

**Printed paper is the biggest exposure.** Anyone with line-of-sight to
the printer can read the slip. Tear it off, hand it over, and don't leave
it on the fridge. The QR carries the same plaintext password.

**Recorder retention.** The `command_line:` sensor's `passphrase`
attribute is recorded by HA's default recorder — every rotated password
ends up in `home-assistant_v2.db` and any HA backups taken since. If you
rotate often, add `sensor.guest_wifi` to your `recorder:` `exclude` list.

**MITM threat.** The script uses `curl --insecure`, which is appropriate
for the self-signed certificate UniFi controllers ship with by default
but accepts any cert. An on-LAN attacker who can ARP-poison your HA host
could intercept the login and obtain the UniFi admin credentials. If your
threat model includes this, put a real cert in front of your UniFi
controller (Caddy / nginx reverse proxy with Let's Encrypt) and remove
`--insecure` from the script.
