DOMAIN = "escpos_printer"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TIMEOUT = "timeout"
CONF_CODEPAGE = "codepage"
CONF_DEFAULT_ALIGN = "default_align"
CONF_DEFAULT_CUT = "default_cut"
CONF_KEEPALIVE = "keepalive"
CONF_STATUS_INTERVAL = "status_interval"
CONF_PROFILE = "profile"
CONF_LINE_WIDTH = "line_width"

# Connection type configuration
CONF_CONNECTION_TYPE = "connection_type"
CONNECTION_TYPE_NETWORK = "network"
CONNECTION_TYPE_USB = "usb"

# USB configuration keys
CONF_VENDOR_ID = "vendor_id"
CONF_PRODUCT_ID = "product_id"
CONF_IN_EP = "in_ep"
CONF_OUT_EP = "out_ep"

# Default values
DEFAULT_PORT = 9100
DEFAULT_TIMEOUT = 4.0
DEFAULT_ALIGN = "left"
DEFAULT_CUT = "none"
DEFAULT_LINE_WIDTH = 48
DEFAULT_CODEPAGE = "CP437"

# USB defaults
DEFAULT_IN_EP = 0x82
DEFAULT_OUT_EP = 0x01

# Known thermal printer vendor IDs for auto-discovery
# Source: http://www.linux-usb.org/usb.ids
THERMAL_PRINTER_VIDS: set[int] = {
    0x0404,  # NCR Corp (7167/7197 Receipt Printers)
    0x04B8,  # Seiko Epson Corp (TM-T88, TM-T20, TM-T70, TM-L100)
    0x04C5,  # Fujitsu, Ltd (KD02906 Line Thermal Printer)
    0x0519,  # Star Micronics Co., Ltd (TSP100, TSP600, TSP700)
    0x06BC,  # Oki Data Corp (OKIPOS 411/412 POS Printer)
    0x0828,  # Sato Corp (WS408 Label Printer)
    0x08BD,  # Citizen Watch Co., Ltd (CLP-521 Label Printer)
    0x0922,  # Dymo-CoStar Corp (LabelWriter series)
    0x0A5F,  # Zebra Technologies (GK420d, ZD410, ZD500, ZM400)
    0x0AA7,  # Wincor Nixdorf (TH210, TH220, TH320, TH420 POS Printers)
    0x0B0B,  # Datamax-O'Neil (E-4304 Label Printer)
    0x0DD4,  # Custom Engineering SPA (K80 80mm Thermal Printer)
    0x0FE6,  # Generic POS Printers (USB Receipt Printer)
    0x1203,  # TSC Auto ID Technology (TTP-245C)
    0x1504,  # Bixolon CO LTD (SRP series)
    0x154F,  # SNBC CO., Ltd (BTP series)
    0x1D90,  # Citizen (CT-E351, PPU-700, CL-S631)
    0x2730,  # Citizen (CT-S2000/4000/310, CLP-521/621/631, CL-S700)
    0x2D84,  # Zhuhai Poskey Technology (DT-108B Thermal Label Printer)
    0x0416,  # Winbond Electronics (some generic Chinese POS-58/80 printers)
}

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
