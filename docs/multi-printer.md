# Multiple Printers

Add the integration once per printer. Each gets its own device, binary sensor, notify entity, and battery sensor (BT only). Connection types can mix freely (e.g. one Network printer + one Bluetooth).

## Targeting in service calls

Most services accept a `target:` block. Targets resolve to one or more config entries; the service runs against each.

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

### By area

```yaml
service: escpos_printer.print_text
target:
  area_id: kitchen
data:
  text: "Everything in the kitchen area"
```

### By entity

```yaml
service: escpos_printer.print_text
target:
  entity_id: binary_sensor.office_printer_online
data:
  text: "Resolved via the entity's owning device"
```

### Broadcast to all printers

Omit `target:` to send to every loaded entry:

```yaml
service: escpos_printer.print_text
data:
  text: "Broadcast to all printers!"
```

## Finding device IDs

1. **Settings → Devices & services**
2. Click **ESC/POS Thermal Printer**
3. Click your printer
4. The device ID is in the URL: `/config/devices/device/<DEVICE_ID>`

## Assigning printers to areas

1. **Settings → Devices & services**
2. Click your printer device
3. Click the pencil icon → pick an area

This lets you target by `area_id:` in service calls.
