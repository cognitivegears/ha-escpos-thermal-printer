"""Device action type constants for ESC/POS Thermal Printer."""

from __future__ import annotations

# Action types
ACTION_PRINT_TEXT_UTF8 = "print_text_utf8"
ACTION_PRINT_TEXT = "print_text"
ACTION_PRINT_QR = "print_qr"
ACTION_PRINT_IMAGE = "print_image"
ACTION_PRINT_BARCODE = "print_barcode"
ACTION_FEED = "feed"
ACTION_CUT = "cut"
ACTION_BEEP = "beep"

ACTION_TYPES = {
    ACTION_PRINT_TEXT_UTF8,
    ACTION_PRINT_TEXT,
    ACTION_PRINT_QR,
    ACTION_PRINT_IMAGE,
    ACTION_PRINT_BARCODE,
    ACTION_FEED,
    ACTION_CUT,
    ACTION_BEEP,
}
