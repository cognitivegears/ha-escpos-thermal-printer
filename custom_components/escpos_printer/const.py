DOMAIN = "escpos_printer"

# Configuration keys
CONF_CUPS_SERVER = "cups_server"
CONF_PRINTER_NAME = "printer_name"
CONF_TIMEOUT = "timeout"
CONF_CODEPAGE = "codepage"
CONF_DEFAULT_ALIGN = "default_align"
CONF_DEFAULT_CUT = "default_cut"
CONF_KEEPALIVE = "keepalive"
CONF_STATUS_INTERVAL = "status_interval"
CONF_PROFILE = "profile"
CONF_LINE_WIDTH = "line_width"

# Default values
DEFAULT_TIMEOUT = 4.0
DEFAULT_ALIGN = "left"
DEFAULT_CUT = "none"
DEFAULT_LINE_WIDTH = 48
DEFAULT_CODEPAGE = "CP437"

# Profile selection constants (also defined in capabilities.py, imported here for convenience)
PROFILE_AUTO = ""  # Auto-detect (default) profile
PROFILE_CUSTOM = "__custom__"  # Custom profile option
OPTION_CUSTOM = "__custom__"  # Custom option for codepage/line_width dropdowns

# Common supported codepages (backward compatibility fallback)
# NOTE: Dynamic codepage loading is now available via capabilities.py
CODEPAGE_CHOICES: list[str] = [
    "CP437",
    "CP932",
    "CP851",
    "CP850",
    "CP852",
    "CP858",
    "CP1252",
    "ISO_8859-1",
    "ISO_8859-7",
    "ISO_8859-15",
]

# Common line widths (backward compatibility fallback)
# NOTE: Dynamic line width loading is now available via capabilities.py
LINE_WIDTH_CHOICES: list[int] = [32, 42, 48, 64]

SERVICE_PRINT_TEXT = "print_text"
SERVICE_PRINT_TEXT_UTF8 = "print_text_utf8"
SERVICE_PRINT_QR = "print_qr"
SERVICE_PRINT_IMAGE = "print_image"
SERVICE_FEED = "feed"
SERVICE_CUT = "cut"
SERVICE_PRINT_BARCODE = "print_barcode"
SERVICE_BEEP = "beep"

ATTR_TEXT = "text"
ATTR_ALIGN = "align"
ATTR_BOLD = "bold"
ATTR_UNDERLINE = "underline"
ATTR_WIDTH = "width"
ATTR_HEIGHT = "height"
ATTR_ENCODING = "encoding"
ATTR_CUT = "cut"
ATTR_FEED = "feed"
ATTR_DATA = "data"
ATTR_SIZE = "size"
ATTR_EC = "ec"
ATTR_IMAGE = "image"
ATTR_HIGH_DENSITY = "high_density"
ATTR_LINES = "lines"
ATTR_MODE = "mode"

# Barcode-related
ATTR_CODE = "code"
ATTR_BC = "bc"
ATTR_BARCODE_HEIGHT = "height"
ATTR_BARCODE_WIDTH = "width"
ATTR_POS = "pos"
ATTR_FONT = "font"
ATTR_ALIGN_CT = "align_ct"
ATTR_CHECK = "check"
ATTR_FORCE_SOFTWARE = "force_software"

# Beep-related
ATTR_TIMES = "times"
ATTR_DURATION = "duration"
