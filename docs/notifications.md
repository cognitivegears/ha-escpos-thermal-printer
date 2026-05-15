# Notifications

Each configured printer gets a `notify.*` entity. You can target it like any other notify service.

Entity-name examples:
- Network: `notify.esc_pos_printer_192_168_1_100_9100`
- USB: `notify.esc_pos_printer_usb_04b8_0e03`
- Bluetooth: `notify.esc_pos_printer_aa_bb_cc_dd_ee_ff`

## Send a basic notification

```yaml
service: notify.send_message
data:
  entity_id: notify.esc_pos_printer_192_168_1_100_9100
  message: "Hello from notifications!"
```

## Notification with title

```yaml
service: notify.send_message
data:
  entity_id: notify.esc_pos_printer_192_168_1_100_9100
  message: |
    System check completed.
    All sensors operational.
  title: "System Status"
```

## Formatted notification (`print_message` entity service)

`notify.send_message` only supports message + title. For full formatting (bold, underline, width, height, alignment, cut, feed, UTF-8 transcoding) use the `escpos_printer.print_message` entity service:

```yaml
service: escpos_printer.print_message
target:
  entity_id: notify.esc_pos_printer_192_168_1_100_9100
data:
  message: "ALERT: Temperature threshold exceeded!"
  title: "Warning"
  bold: true
  width: double
  height: double
  align: center
  cut: partial
```

## Notification with UTF-8 transcoding

```yaml
service: escpos_printer.print_message
target:
  entity_id: notify.esc_pos_printer_192_168_1_100_9100
data:
  message: "Today's special: Creme brulee & souffle"
  utf8: true
  align: center
  cut: partial
```

## Use in an automation

```yaml
automation:
  - alias: "Print Low Battery Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.device_battery
        below: 20
    action:
      - service: escpos_printer.print_message
        target:
          entity_id: notify.esc_pos_printer_192_168_1_100_9100
        data:
          message: "Battery low: {{ states('sensor.device_battery') }}%"
          title: "Low Battery Warning"
          bold: true
          cut: partial
```
