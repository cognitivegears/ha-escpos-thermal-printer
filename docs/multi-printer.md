# Multiple Printers

Add the integration once per printer. Each gets its own device, binary sensor, notify entity, and battery sensor (BT only, disabled by default). Connection types can mix freely (e.g. one Network printer + one Bluetooth).

## Targeting in service calls

Printers are targeted with Home Assistant's standard `target:` block (new in 1.2.0): pick devices, entities, areas, floors, or labels, and every ESC/POS printer they resolve to is printed on. This also means the print services now show up in the entity/device "Add to… → Create as a new action" pickers.

Passing **`device_id`** directly in `data:` (the only form supported before 1.2.0) keeps working exactly as before — existing automations and scripts need no changes.

### Specific printer

```yaml
service: escpos_printer.print_text
target:
  device_id: a1b2c3d4e5f6
data:
  text: "Sent to one printer only"
```

### Multiple specific printers

```yaml
service: escpos_printer.print_text
target:
  device_id:
    - printer1_device_id
    - printer2_device_id
data:
  text: "Sent to both printers"
```

### All printers in an area

```yaml
service: escpos_printer.print_text
target:
  area_id: kitchen
data:
  text: "Sent to every ESC/POS printer in the Kitchen"
```

Non-printer devices in the area are ignored. A target that resolves to no
ESC/POS printer at all (e.g. an empty area) is rejected with a validation
error. Floors and labels work the same way. Targeting a printer's notify
entity is equivalent to targeting its device — the entity picker offers the
same printer either way.

### Legacy `device_id` plus a target: union, not replace

A call can carry a legacy `device_id` in `data:` **and** a picker target
(entity/area/floor/label) at the same time — the two are **unioned**, not
one replacing the other, so every printer resolved by either one prints.

This matters for automations built in the UI before 1.2.0: their `device_id`
was stored inside `data:` (not the newer `target:` block), so opening one of
those automations in the editor now shows an empty target picker even though
the call still works exactly as before. Adding a picker target on top of
that stored `device_id` prints to both, not just the new target.

### Broadcast to all printers

Omit `target:` (and the `broadcast` field) to send to every loaded entry, kept for backward compatibility:

```yaml
service: escpos_printer.print_text
data:
  text: "Broadcast to all printers!"
```

If more than one printer is configured, omitting the target logs a warning
(`no target specified — printing to all N configured printers`) so an
automation that only meant to target one printer doesn't silently print
everywhere. This implicit fallback is deprecated and will be removed in
2.0.0 — use `broadcast: true` to send to all printers on purpose:

```yaml
service: escpos_printer.print_text
data:
  broadcast: true
  text: "Broadcast to all printers, explicitly"
```

`broadcast: true` and any target (`device_id`, `entity_id`, `area_id`,
`floor_id`, `label_id`) are mutually exclusive; combining them is rejected
before the service runs.

## Finding device IDs

1. **Settings → Devices & services**
2. Click **ESC/POS Thermal Printer**
3. Click your printer
4. The device ID is in the URL: `/config/devices/device/<DEVICE_ID>`

## Assigning printers to areas

Assign a printer device to an area (**Settings → Devices & services** → your printer → pencil icon → pick an area) and, since 1.2.0, service calls can target that area directly with `target: area_id:`.
