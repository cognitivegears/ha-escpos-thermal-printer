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

### TODO Item
**Inputs:** printer · `todo_entity` · `box_style` · `max_items_per_trigger` · `cut_per_item`
**Notes:** HA does not fire per-item events for todo lists; the blueprint compares the entity's `items` attribute between the previous and current state and prints what's new. `max_items_per_trigger` is a safety cap against bulk-sync floods. `cut_per_item: false` keeps a batch of items on one slip with a single cut at the end.

## Modifying a blueprint

Each blueprint is a single YAML file. Fork the repo, edit the file, and import the raw URL from your fork. Or copy the YAML into HA's `<config>/blueprints/script/` or `<config>/blueprints/automation/` directly and edit in place — HA picks it up on the next reload.

The validator at [`scripts/validate_blueprints.py`](../scripts/validate_blueprints.py) is a useful smoke test if you're authoring new blueprints — it parses the YAML and checks the required `blueprint.*` fields:

```sh
python scripts/validate_blueprints.py blueprints
```
