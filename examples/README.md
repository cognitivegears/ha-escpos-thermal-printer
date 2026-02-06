# ESC/POS Printer Integration Examples

Example scripts demonstrating how to use the ESC/POS Thermal Printer integration with Home Assistant.

## Available Examples

### 1. Test Printer Scripts (`test_printer_script.yaml`)

Comprehensive test scripts for verifying printer functionality:
- **test_escpos_printer** - Full feature test (text, alignment, formatting, QR, barcode, image)
- **test_escpos_quick** - Quick text print test
- **test_escpos_qr** - QR code test
- **test_escpos_barcode** - Barcode test
- **test_escpos_image** - Image print test
- **test_escpos_beep** - Buzzer test
- **test_escpos_receipt_demo** - Sample receipt-style printout

### 2. Mealie Shopping List Printer (`mealie_shopping_list_printer.yaml`)

Print your Mealie shopping list to a receipt printer with AI-powered categorization.

**Features:**
- Fetches shopping list from Mealie via the Home Assistant Mealie integration
- Sends items to OpenAI for smart categorization by grocery store section
- Prints a nicely formatted receipt with checkboxes for each item

**Prerequisites:**
1. [Mealie integration](https://github.com/mealie-recipes/mealie) installed via HACS
2. [OpenAI Conversation integration](https://www.home-assistant.io/integrations/openai_conversation/) configured
3. This ESC/POS Thermal Printer integration installed and configured

**Script:** `print_mealie_shopping_list`

**Options (all optional with defaults):**
| Field | Default | Description |
|-------|---------|-------------|
| `shopping_list_entity` | `todo.mealie_shopping_list` | Mealie todo entity to print |
| `openai_agent_id` | `conversation.chatgpt` | OpenAI conversation agent |
| `printer_device_id` | All printers | Target specific printer |

## Installation

1. Copy the desired `.yaml` file to your Home Assistant config directory
2. Include it in your `configuration.yaml`:

```yaml
script: !include examples/mealie_shopping_list_printer.yaml
```

## Example Dashboard Button
```yaml
type: button
name: Print Shopping List
icon: mdi:printer-pos
tap_action:
  action: call-service
  service: script.print_mealie_shopping_list
  data:
    shopping_list_entity: todo.mealie_shopping_list
    openai_agent_id: conversation.chatgpt
    # printer_device_id: optional - omit to use all printers
```
