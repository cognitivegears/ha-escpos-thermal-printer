from __future__ import annotations

from typing import Any

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
# Opt-in: allow image URLs that resolve to private/LAN/loopback addresses.
# Off by default so an upgrade never silently turns the integration into an
# SSRF proxy; cloud-metadata / link-local ranges stay blocked even when on.
CONF_ALLOW_LOCAL_IMAGE_URLS = "allow_local_image_urls"

# Connection type configuration
CONF_CONNECTION_TYPE = "connection_type"
CONNECTION_TYPE_NETWORK = "network"
CONNECTION_TYPE_USB = "usb"
CONNECTION_TYPE_BLUETOOTH = "bluetooth"

# USB configuration keys
CONF_VENDOR_ID = "vendor_id"
CONF_PRODUCT_ID = "product_id"
CONF_IN_EP = "in_ep"
CONF_OUT_EP = "out_ep"

# Bluetooth configuration keys
CONF_BT_MAC = "bt_mac"
CONF_BT_DEVICE = "bt_device"
CONF_RFCOMM_CHANNEL = "rfcomm_channel"

# Sentinel value for the manual-MAC-entry choice in the BT picker dropdown.
BT_MANUAL_ENTRY_KEY = "__manual__"

# Sentinel for "show all paired devices, not just imaging-class" in the picker.
BT_SHOW_ALL_KEY = "__show_all__"

# Default values
DEFAULT_PORT = 9100
DEFAULT_TIMEOUT = 4.0
DEFAULT_ALIGN = "left"
DEFAULT_CUT = "none"
DEFAULT_LINE_WIDTH = 48
DEFAULT_CODEPAGE = "CP437"
DEFAULT_ALLOW_LOCAL_IMAGE_URLS = False

# USB defaults
DEFAULT_IN_EP = 0x82
DEFAULT_OUT_EP = 0x01

# Bluetooth defaults
DEFAULT_RFCOMM_CHANNEL = 1

# Known thermal printer vendor IDs for auto-discovery.
# Source: http://www.linux-usb.org/usb.ids
# `manifest.json`'s `usb` block is generated from this set by
# `scripts/sync_manifest_requirements.py` — keep this list authoritative.
THERMAL_PRINTER_VIDS: frozenset[int] = frozenset(
    {
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
)

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
SERVICE_PRINT_CAMERA_SNAPSHOT = "print_camera_snapshot"
SERVICE_PRINT_IMAGE_ENTITY = "print_image_entity"
SERVICE_PRINT_IMAGE_URL = "print_image_url"
SERVICE_PRINT_IMAGE_PATH = "print_image_path"
SERVICE_PREVIEW_IMAGE = "preview_image"
SERVICE_CALIBRATION_PRINT = "calibration_print"
SERVICE_FEED = "feed"
SERVICE_CUT = "cut"
SERVICE_PRINT_BARCODE = "print_barcode"
SERVICE_BEEP = "beep"
SERVICE_PRINT_BOX = "print_box"
SERVICE_PRINT_TABLE = "print_table"
SERVICE_PRINT_TEXT_IMAGE = "print_text_image"
SERVICE_PRINT_SEPARATOR = "print_separator"
SERVICE_PRINT_KVTABLE = "print_kvtable"
SERVICE_PREVIEW_BOX = "preview_box"
SERVICE_PREVIEW_TABLE = "preview_table"

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

# Image-related (v2)
ATTR_IMAGE_WIDTH = "image_width"
ATTR_ROTATION = "rotation"
ATTR_DITHER = "dither"
ATTR_THRESHOLD = "threshold"
ATTR_IMPL = "impl"
ATTR_CENTER = "center"
ATTR_AUTOCONTRAST = "autocontrast"
ATTR_FRAGMENT_HEIGHT = "fragment_height"
ATTR_CHUNK_DELAY_MS = "chunk_delay_ms"
ATTR_INVERT = "invert"
ATTR_MIRROR = "mirror"
ATTR_AUTO_RESIZE = "auto_resize"
ATTR_FALLBACK_IMAGE = "fallback_image"

# Text-effects (box / table / text-image).
ATTR_STYLE = "style"
ATTR_PADDING = "padding"
ATTR_ROWS = "rows"
ATTR_COLUMN_WIDTHS = "column_widths"
ATTR_COLUMN_ALIGNS = "column_aligns"
ATTR_HEADER = "header"
ATTR_ROW_SEPARATORS = "row_separators"
# Total printed width (in columns) including borders. Shared between
# print_box, print_table, and print_kvtable so all three services use one
# consistent name for "the outer width of the rendered block."
ATTR_TOTAL_WIDTH = "total_width"
# ``ATTR_FONT`` already exists for the barcode "A"/"B" font selector;
# the text-image service uses ``ATTR_FONT_NAME`` to avoid clashing.
ATTR_FONT_NAME = "font"
ATTR_FONT_PATH = "font_path"
ATTR_FONT_SIZE = "font_size"
ATTR_LINE_SPACING = "line_spacing"

# print_separator
ATTR_CHAR = "char"
ATTR_REPEAT = "repeat"

# print_kvtable
ATTR_ITEMS = "items"
ATTR_LABEL_WIDTH = "label_width"
ATTR_VALUE_ALIGN = "value_align"

# preview_box / preview_table
ATTR_OUTPUT_PATH = "output_path"

# Border-style choices for print_box / print_table. Mirrored in
# ``services.yaml`` selectors and the voluptuous schemas. ``auto``
# adapts to the printer codepage; ``none`` disables borders entirely.
BORDER_STYLES: frozenset[str] = frozenset(
    {"auto", "single", "double", "ascii", "asterisk", "hash", "none"}
)
DEFAULT_BORDER_STYLE = "auto"

# Bundled font names exposed via the ``font`` selector of
# ``print_text_image``. A-M3: kept literal here (importing
# ``text_effects.font_render`` would create a circular import through
# ``security``); parity with the renderer's ``_BUILTIN_FONT_FILES`` is
# enforced by ``tests/text_effects/test_font_render.py``
# (``test_builtin_font_choices_match_renderer``). The renderer now
# *raises* on an unknown name (A-M3 — silent fallback removed) so any
# drift fails loudly instead of silently swapping to the default mono.
#
# B-M3 (deferred): the string-choice sets (CONNECTION_TYPE_*,
# BORDER_STYLES, DITHER_MODES, IMPL_MODES, BUILTIN_FONT_CHOICES) could
# be `enum.StrEnum` for typed iteration + voluptuous-direct use. Defer
# the multi-file refactor until a third drift incident makes the
# payoff clear; the parity tests above + the schema-level `vol.In(...)`
# already catch the typical "I added a value to one place but not the
# other" mistake.
BUILTIN_FONT_CHOICES: tuple[str, ...] = ("dejavu_mono", "dejavu_sans", "dejavu_serif")
DEFAULT_FONT_NAME = "dejavu_mono"
DEFAULT_FONT_SIZE = 16
DEFAULT_LINE_SPACING = 1.1

# Image v2 defaults.
#
# - ``DEFAULT_FRAGMENT_HEIGHT = 256`` is a tuning constant carried over from
#   issue #45 (python-escpos buffer overruns on very tall images). 256-px
#   slices keep the per-write payload under most printers' buffer.
# - ``DEFAULT_CHUNK_DELAY_MS_BLUETOOTH = 50`` is the per-slice wait from
#   issue #43 (slow Bluetooth-SPP printers needed time to drain the buffer
#   between writes). The schema leaves the field unset by default so the
#   adapter substitutes its per-transport default (Network/USB: ``0``;
#   Bluetooth: ``50``).
# - ``DEFAULT_DITHER = "floyd-steinberg"`` is dithered *in this integration*
#   (see ``image_processor.process_image``) — not delegated to
#   ``python-escpos``.
# - Bounds (``IMAGE_WIDTH_MIN``/``IMAGE_THRESHOLD_MIN``/...) live in
#   ``security.py`` so the schema and the validators share one source of
#   truth. ``services.yaml`` selectors must mirror those bounds.
DEFAULT_FRAGMENT_HEIGHT = 256
# ``DEFAULT_CHUNK_DELAY_MS = None`` is the schema-level "no explicit value"
# sentinel; the adapter substitutes its per-transport default (Network/USB:
# ``0``; Bluetooth: ``50``). Pre-existing code that imports the int default
# can still rely on ``DEFAULT_CHUNK_DELAY_MS_BLUETOOTH`` below.
DEFAULT_CHUNK_DELAY_MS_NETWORK = 0
DEFAULT_CHUNK_DELAY_MS_BLUETOOTH = 50
DEFAULT_DITHER = "floyd-steinberg"
DEFAULT_IMPL = "bitImageRaster"
DEFAULT_THRESHOLD = 128

DITHER_MODES: frozenset[str] = frozenset({"floyd-steinberg", "none", "threshold"})
IMPL_MODES: frozenset[str] = frozenset({"bitImageRaster", "graphics", "bitImageColumn"})
ROTATION_VALUES: frozenset[int] = frozenset({0, 90, 180, 270})

# Reliability profile presets used by the options flow.
# A profile picks fragment_height + chunk_delay_ms + impl; the user can
# still override any of these per service call.
RELIABILITY_PROFILE_AUTO = "auto"
RELIABILITY_PROFILE_FAST_LAN = "fast_lan"
RELIABILITY_PROFILE_BALANCED = "balanced"
RELIABILITY_PROFILE_CONSERVATIVE = "conservative"
RELIABILITY_PROFILE_BLUETOOTH = "bluetooth_safe"
CONF_RELIABILITY_PROFILE = "reliability_profile"

RELIABILITY_PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    RELIABILITY_PROFILE_AUTO: {},
    RELIABILITY_PROFILE_FAST_LAN: {
        "fragment_height": 512,
        "chunk_delay_ms": 0,
        "impl": "bitImageRaster",
    },
    RELIABILITY_PROFILE_BALANCED: {
        "fragment_height": 256,
        "chunk_delay_ms": 20,
        "impl": "bitImageRaster",
    },
    RELIABILITY_PROFILE_CONSERVATIVE: {
        "fragment_height": 128,
        "chunk_delay_ms": 100,
        "impl": "bitImageRaster",
    },
    RELIABILITY_PROFILE_BLUETOOTH: {
        "fragment_height": 128,
        "chunk_delay_ms": 150,
        "impl": "bitImageRaster",
    },
}
