# Automation Examples

For service parameter reference, see [services.md](services.md). For multi-printer targeting, see [multi-printer.md](multi-printer.md).

## Door access logger

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

## Temperature alert

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

            *************************
          bold: true
          align: center
          cut: partial
          feed: 2
```

## Scheduled morning report

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

## Kitchen order ticket (targeted)

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

## Emergency broadcast (all printers)

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

## Shopping list

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

## Receipt with mixed formatting

```yaml
sequence:
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
      align: center

  # Items
  - service: escpos_printer.print_text
    data:
      text: |
        ================================
        Item 1                    $10.00
        Item 2                    $15.00
        --------------------------------
        TOTAL                     $25.00

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
