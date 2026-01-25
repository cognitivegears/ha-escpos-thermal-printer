# Examples

This document contains detailed examples for using the ESC/POS Thermal Printer integration.

**Note:** All examples work identically for both network and USB connected printers. The services and parameters are the same regardless of connection type.

## Table of Contents

- [Basic Printing](#basic-printing)
- [Text Formatting](#text-formatting)
- [QR Codes and Barcodes](#qr-codes-and-barcodes)
- [Images](#images)
- [Receipts and Reports](#receipts-and-reports)
- [Multiple Printers](#multiple-printers)
- [Home Assistant Automations](#home-assistant-automations)
- [Notifications](#notifications)

---

## Basic Printing

### Simple Text

```yaml
service: escpos_printer.print_text
data:
  text: "Hello, World!"
```

### Text with Line Break

```yaml
service: escpos_printer.print_text
data:
  text: |
    Line 1
    Line 2
    Line 3
```

### Print and Cut

```yaml
service: escpos_printer.print_text
data:
  text: "This receipt will be cut"
  cut: partial
```

### Print with Paper Feed

```yaml
service: escpos_printer.print_text
data:
  text: "Some space after this"
  feed: 3
```

---

## Text Formatting

### Bold Text

```yaml
service: escpos_printer.print_text
data:
  text: "IMPORTANT NOTICE"
  bold: true
```

### Centered Text

```yaml
service: escpos_printer.print_text
data:
  text: "Centered Text"
  align: center
```

### Large Text (Double Width and Height)

```yaml
service: escpos_printer.print_text
data:
  text: "BIG TEXT"
  width: double
  height: double
  align: center
```

### Underlined Text

```yaml
service: escpos_printer.print_text
data:
  text: "Underlined"
  underline: single
```

### Combined Formatting

```yaml
service: escpos_printer.print_text
data:
  text: "SALE"
  bold: true
  width: double
  height: double
  align: center
  underline: double
```

### UTF-8 Text with Special Characters

Use `print_text_utf8` for text with special characters like curly quotes,
accented letters, or symbols:

```yaml
service: escpos_printer.print_text_utf8
data:
  text: "Cafe menu: Creme brulee, souffle, crepes"
  align: center
```

The service automatically converts characters that your printer can't handle directly.

---

## QR Codes and Barcodes

### Basic QR Code

```yaml
service: escpos_printer.print_qr
data:
  data: "https://example.com"
  size: 6
```

### QR Code with High Error Correction

```yaml
service: escpos_printer.print_qr
data:
  data: "https://example.com/important"
  size: 8
  ec: H
  align: center
```

### EAN-13 Barcode

```yaml
service: escpos_printer.print_barcode
data:
  code: "4006381333931"
  bc: EAN13
  height: 80
  width: 3
  pos: BELOW
```

### CODE128 Barcode

```yaml
service: escpos_printer.print_barcode
data:
  code: "ABC-12345"
  bc: CODE128
  height: 60
  width: 2
  pos: BELOW
  align: center
```

### UPC-A Barcode

```yaml
service: escpos_printer.print_barcode
data:
  code: "012345678905"
  bc: UPC-A
  height: 70
  pos: BELOW
```

---

## Images

### Local Image

```yaml
service: escpos_printer.print_image
data:
  image: "/config/www/logo.png"
  align: center
```

### Image from URL

```yaml
service: escpos_printer.print_image
data:
  image: "https://example.com/logo.png"
  align: center
```

### Image with Low Density (Faster Print)

```yaml
service: escpos_printer.print_image
data:
  image: "/config/www/logo.png"
  high_density: false
```

**Tips for images:**

- Keep width under 512 pixels (will be auto-resized if larger)
- Use PNG or JPEG format
- Black and white images work best
- Simple graphics print better than photos

---

## Receipts and Reports

### Simple Receipt

```yaml
service: escpos_printer.print_text
data:
  text: |
    ================================
              ACME STORE
    ================================

    Coffee               $3.50
    Muffin               $2.75
    --------------------------------
    Total                $6.25

    Thank you for your purchase!

    {{ now().strftime('%Y-%m-%d %H:%M') }}
  align: left
  cut: full
  feed: 2
```

### Receipt with Header Formatting

This uses multiple service calls for different formatting:

```yaml
# Header
- service: escpos_printer.print_text
  data:
    text: "STORE NAME"
    bold: true
    width: double
    height: double
    align: center

# Address
- service: escpos_printer.print_text
  data:
    text: |
      123 Main Street
      City, State 12345
      Tel: (555) 123-4567
    align: center

# Separator
- service: escpos_printer.print_text
  data:
    text: "================================"

# Items
- service: escpos_printer.print_text
  data:
    text: |
      Item 1                    $10.00
      Item 2                    $15.00
      Item 3                     $8.50
      --------------------------------
      Subtotal                  $33.50
      Tax (8%)                   $2.68
      --------------------------------
      TOTAL                     $36.18

# Footer with QR
- service: escpos_printer.print_qr
  data:
    data: "https://example.com/receipt/12345"
    size: 4
    align: center

- service: escpos_printer.print_text
  data:
    text: "Scan for digital receipt"
    align: center
    cut: partial
    feed: 2
```

### Daily Report

```yaml
service: escpos_printer.print_text
data:
  text: |
    ================================
           DAILY SUMMARY
    ================================
    Date: {{ now().strftime('%A, %B %d, %Y') }}

    TEMPERATURE
    Current: {{ states('sensor.temperature') }} F
    High:    {{ state_attr('sensor.temperature', 'max') }} F
    Low:     {{ state_attr('sensor.temperature', 'min') }} F

    HUMIDITY
    Current: {{ states('sensor.humidity') }}%

    ENERGY
    Today:   {{ states('sensor.daily_energy') }} kWh

    ================================
  cut: full
  feed: 3
```

### Visitor Log Entry

```yaml
service: escpos_printer.print_text
data:
  text: |
    -------- VISITOR LOG --------

    Date: {{ now().strftime('%Y-%m-%d') }}
    Time: {{ now().strftime('%H:%M:%S') }}

    Door: Front Entrance
    Status: OPENED

    -----------------------------
  cut: partial
  feed: 1
```

---

## Multiple Printers

### Target a Specific Printer

```yaml
service: escpos_printer.print_text
target:
  device_id: a1b2c3d4e5f6
data:
  text: "Sent to one printer only"
```

Find your device ID in **Settings** > **Devices & services** > click on your printer.

### Target Multiple Printers

```yaml
service: escpos_printer.print_text
target:
  device_id:
    - printer1_device_id
    - printer2_device_id
data:
  text: "Sent to two printers"
```

### Broadcast to All Printers

Omit the `target` parameter to send to all configured printers:

```yaml
service: escpos_printer.print_text
data:
  text: "Broadcast to all printers!"
```

### Target by Area

If your printers are assigned to areas:

```yaml
service: escpos_printer.print_text
target:
  area_id: kitchen
data:
  text: "Sent to all printers in the kitchen"
```

### Target by Entity

```yaml
service: escpos_printer.print_text
target:
  entity_id: binary_sensor.office_printer_online
data:
  text: "Sent via entity targeting"
```

---

## Home Assistant Automations

### Door Access Logger

```yaml
automation:
  - alias: "Log Front Door Access"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            -------- ACCESS LOG --------
            Time: {{ now().strftime('%H:%M:%S') }}
            Date: {{ now().strftime('%Y-%m-%d') }}
            Door: Front Door
            Event: OPENED
            ----------------------------
          cut: partial
          feed: 1
```

### Temperature Alert

```yaml
automation:
  - alias: "High Temperature Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.temperature
        above: 85
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            *** TEMPERATURE ALERT ***

            Current: {{ states('sensor.temperature') }} F
            Threshold: 85 F
            Time: {{ now().strftime('%H:%M') }}
            Location: {{ state_attr('sensor.temperature', 'friendly_name') }}

            *************************
          bold: true
          align: center
          cut: partial
          feed: 2
```

### Scheduled Daily Report

```yaml
automation:
  - alias: "Print Morning Report"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            ================================
                   MORNING REPORT
            ================================
            {{ now().strftime('%A, %B %d, %Y') }}

            Weather: {{ states('weather.home') }}
            Temp: {{ state_attr('weather.home', 'temperature') }} F

            Calendar:
            {{ states('sensor.calendar_today') }}

            ================================
          cut: full
          feed: 3
```

### Package Delivery Notification

```yaml
automation:
  - alias: "Package Delivered"
    trigger:
      - platform: state
        entity_id: binary_sensor.mailbox
        to: "on"
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            *** PACKAGE ALERT ***

            Delivery detected!
            Time: {{ now().strftime('%H:%M') }}

            Check the mailbox.
          align: center
          cut: partial
```

### Kitchen Order Ticket (Targeted)

```yaml
automation:
  - alias: "Print Kitchen Order"
    trigger:
      - platform: event
        event_type: new_order
    action:
      - service: escpos_printer.print_text
        target:
          device_id: kitchen_printer_id
        data:
          text: |
            ================================
                    KITCHEN ORDER
            ================================
            Order: #{{ trigger.event.data.order_id }}
            Time: {{ now().strftime('%H:%M') }}

            {{ trigger.event.data.items }}

            ================================
          bold: true
          cut: full
```

### Emergency Broadcast (All Printers)

```yaml
automation:
  - alias: "Emergency Alert - All Printers"
    trigger:
      - platform: state
        entity_id: input_boolean.emergency_mode
        to: "on"
    action:
      - service: escpos_printer.print_text
        # No target = all printers
        data:
          text: |
            ****************************
            *    EMERGENCY ALERT       *
            ****************************

            {{ states('input_text.emergency_message') }}

            Time: {{ now().strftime('%H:%M:%S') }}

            ****************************
          bold: true
          width: double
          align: center
          cut: partial
          feed: 3
```

### Shopping List

```yaml
automation:
  - alias: "Print Shopping List"
    trigger:
      - platform: state
        entity_id: input_button.print_shopping_list
    action:
      - service: escpos_printer.print_text
        data:
          text: |
            ================================
                   SHOPPING LIST
            ================================
            {{ now().strftime('%Y-%m-%d') }}

            {% for item in state_attr('todo.shopping_list', 'items') %}
            [ ] {{ item.name }}
            {% endfor %}

            ================================
          cut: full
          feed: 2
```

---

## Notifications

The integration creates a notification entity for each printer.

**Entity naming:**
- Network printers: `notify.esc_pos_printer_192_168_1_100_9100`
- USB printers: `notify.esc_pos_printer_usb_04b8_0e03` (based on VID:PID)

### Send a Notification

```yaml
service: notify.send_message
data:
  entity_id: notify.esc_pos_printer_192_168_1_100_9100
  message: "Hello from notifications!"
```

### Notification with Title

```yaml
service: notify.send_message
data:
  entity_id: notify.esc_pos_printer_192_168_1_100_9100
  message: |
    System check completed.
    All sensors operational.
  title: "System Status"
```

### Use in Automation

```yaml
automation:
  - alias: "Print Low Battery Alert"
    trigger:
      - platform: numeric_state
        entity_id: sensor.device_battery
        below: 20
    action:
      - service: notify.send_message
        data:
          entity_id: notify.esc_pos_printer_192_168_1_100_9100
          message: "Battery low: {{ states('sensor.device_battery') }}%"
          title: "Low Battery Warning"
```

---

## Paper Control

### Feed Paper

```yaml
service: escpos_printer.feed
data:
  lines: 5
```

### Cut Paper

```yaml
service: escpos_printer.cut
data:
  mode: partial
```

Full cut:

```yaml
service: escpos_printer.cut
data:
  mode: full
```

### Beep (If Supported)

```yaml
service: escpos_printer.beep
data:
  times: 3
  duration: 4
```
