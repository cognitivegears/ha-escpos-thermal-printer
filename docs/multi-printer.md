# Multiple Printers

Add the integration once per printer. Each gets its own device, binary sensor, notify entity, and battery sensor (BT only, disabled by default). Connection types can mix freely (e.g. one Network printer + one Bluetooth).

## Targeting in service calls

Printers are targeted by **`device_id`** — either in a `target:` block or directly in `data:`. Each `device_id` resolves to a config entry; the service runs against each. Targeting by `area_id`, `label_id`, or `entity_id` is **not supported** and is rejected with a validation error.

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

### Broadcast to all printers

Omit `target:` (and the `broadcast` field) to send to every loaded entry — kept for backward compatibility:

```yaml
service: escpos_printer.print_text
data:
  text: "Broadcast to all printers!"
```

If more than one printer is configured, omitting the target logs a warning
(`no device_id specified — printing to all N configured printers`) so an
automation that only meant to target one printer doesn't silently print
everywhere. To send to all printers on purpose without the warning, set
`broadcast: true` instead:

```yaml
service: escpos_printer.print_text
data:
  broadcast: true
  text: "Broadcast to all printers, explicitly"
```

`broadcast: true` and `device_id` are mutually exclusive — combining them
is rejected before the service runs.

## Finding device IDs

1. **Settings → Devices & services**
2. Click **ESC/POS Thermal Printer**
3. Click your printer
4. The device ID is in the URL: `/config/devices/device/<DEVICE_ID>`

## Assigning printers to areas

You can assign a printer device to an area for organization (**Settings → Devices & services** → your printer → pencil icon → pick an area), but service calls cannot target by `area_id` — use `device_id`.
