"""Voluptuous schemas for ESC/POS printer services.

Each schema is registered via ``hass.services.async_register(..., schema=...)``
so HA validates user input **before** the handler runs. ``services.yaml``
selectors are purely a UI hint; without these schemas, REST / WebSocket /
Python-script callers bypass all validation. See the Bronze quality-scale
``action-setup`` rule for the requirement.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from homeassistant.components.notify import ATTR_MESSAGE, ATTR_TITLE
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from ..const import (
    ATTR_ALIGN,
    ATTR_ALIGN_CT,
    ATTR_AUTO_RESIZE,
    ATTR_AUTOCONTRAST,
    ATTR_BARCODE_HEIGHT,
    ATTR_BARCODE_WIDTH,
    ATTR_BC,
    ATTR_BOLD,
    ATTR_CENTER,
    ATTR_CHAR,
    ATTR_CHECK,
    ATTR_CHUNK_DELAY_MS,
    ATTR_CODE,
    ATTR_COLUMN_ALIGNS,
    ATTR_COLUMN_WIDTHS,
    ATTR_CUT,
    ATTR_DATA,
    ATTR_DITHER,
    ATTR_DURATION,
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FALLBACK_IMAGE,
    ATTR_FEED,
    ATTR_FONT,
    ATTR_FONT_NAME,
    ATTR_FONT_PATH,
    ATTR_FONT_SIZE,
    ATTR_FORCE_SOFTWARE,
    ATTR_FRAGMENT_HEIGHT,
    ATTR_HEADER,
    ATTR_HEIGHT,
    ATTR_HIGH_DENSITY,
    ATTR_IMAGE,
    ATTR_IMAGE_WIDTH,
    ATTR_IMPL,
    ATTR_INVERT,
    ATTR_ITEMS,
    ATTR_LABEL_WIDTH,
    ATTR_LINE_SPACING,
    ATTR_LINES,
    ATTR_MIRROR,
    ATTR_MODE,
    ATTR_OUTPUT_PATH,
    ATTR_PADDING,
    ATTR_POS,
    ATTR_REPEAT,
    ATTR_ROTATION,
    ATTR_ROW_SEPARATORS,
    ATTR_ROWS,
    ATTR_SIZE,
    ATTR_STYLE,
    ATTR_TEXT,
    ATTR_THRESHOLD,
    ATTR_TIMES,
    ATTR_TOTAL_WIDTH,
    ATTR_UNDERLINE,
    ATTR_VALUE_ALIGN,
    ATTR_WIDTH,
    BORDER_STYLES,
    BUILTIN_FONT_CHOICES,
    DEFAULT_BORDER_STYLE,
    DEFAULT_DITHER,
    DEFAULT_FONT_NAME,
    DEFAULT_FONT_SIZE,
    DEFAULT_LINE_SPACING,
    DEFAULT_THRESHOLD,
    DITHER_MODES,
    IMPL_MODES,
    ROTATION_VALUES,
)
from ..security import (
    IMAGE_CHUNK_DELAY_MAX,
    IMAGE_CHUNK_DELAY_MIN,
    IMAGE_FRAGMENT_MAX,
    IMAGE_FRAGMENT_MIN,
    IMAGE_THRESHOLD_MAX,
    IMAGE_THRESHOLD_MIN,
    IMAGE_WIDTH_MAX,
    IMAGE_WIDTH_MIN,
    MAX_BARCODE_LENGTH,
    MAX_BASE64_INPUT_BYTES,
    MAX_BOX_WIDTH,
    MAX_FEED_LINES,
    MAX_FONT_PATH_LENGTH,
    MAX_FONT_SIZE_PT,
    MAX_IMAGE_PATH_LENGTH,
    MAX_QR_DATA_LENGTH,
    MAX_SEPARATOR_REPEAT,
    MAX_TABLE_CELL_LENGTH,
    MAX_TABLE_COLS,
    MAX_TABLE_ROWS,
    MAX_TEXT_LENGTH,
    MAX_URL_LENGTH,
)

# `device_id` is a free-form field used by handlers to target a specific
# entry (or all entries when omitted). Accept str or [str] to match the
# `selector: device:` and `selector: device: multiple: true` UI shapes.
_DEVICE_ID = vol.Any(cv.string, [cv.string])

# Alignment / underline / cut / size enums shared across services.
_ALIGN = vol.In(["left", "center", "right"])
_UNDERLINE = vol.In(["none", "single", "double"])
_CUT = vol.In(["none", "partial", "full"])

# Width/height accept "normal"|"double"|"triple" or a number 1-8 (the
# UI surfaces both forms). Coerce numeric strings before checking the
# integer range.
_TEXT_SIZE = vol.Any(
    vol.In(["normal", "double", "triple"]),
    vol.All(vol.Coerce(int), vol.Range(min=1, max=8)),
)

_FEED = vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_FEED_LINES))


def _image_source_validator(value: Any) -> Any:
    """Length-cap an image source string before delegating to ``cv.template``.

    ``cv.template`` happily accepts megabyte strings (it constructs a
    Template object), which would defeat the pre-decode size cap in
    ``security.validate_base64_image``. Enforce the cap up front so a
    200 MB base64 string fails at the schema layer.
    """
    if isinstance(value, str) and len(value) > MAX_BASE64_INPUT_BYTES:
        raise vol.Invalid(f"image source too large (max ~{MAX_BASE64_INPUT_BYTES} chars)")
    return cv.template(value)


_IMAGE_SOURCE = _image_source_validator


def _image_option_fragment(
    prefix: str = "",
    *,
    autocontrast: bool = False,
    auto_resize: bool = False,
) -> dict[Any, Any]:
    """Build the image-option fragment keyed with an optional prefix.

    Notify uses ``image_`` to disambiguate from the surrounding text
    options; the plain service call uses bare keys. ``ATTR_IMAGE_WIDTH``
    is already namespaced (``image_width``) so it never gets a prefix.

    ``autocontrast`` / ``auto_resize`` override the schema-level default
    for those two keys so each focused service's voluptuous default can
    match its ``services.yaml`` UI default. Without this override, a UI
    form caller and a YAML-script caller of the same service would get
    different behaviour for the same omitted key.

    B-L9: the returned dict is wrapped in ``MappingProxyType`` at the
    module-cached callsites below so the freeze invariant is visible
    in the source. Without it, a future test fixture could mutate the
    cached dict and silently re-shape every schema that spreads it.
    """

    def k(name: str) -> str:
        if not prefix or name == ATTR_IMAGE_WIDTH:
            return name
        return f"{prefix}{name}"

    # ``chunk_delay_ms`` deliberately has **no default** at the schema
    # layer so the adapter can substitute its per-transport default
    # (Network/USB: 0; Bluetooth: 50). Setting one here would penalize the
    # fast-transport majority with an extra 50 ms per slice for no reason.
    # ``fragment_height`` / ``impl`` also have no schema default so the
    # per-printer reliability profile (options flow) can pick them.
    return {
        vol.Optional(k(ATTR_HIGH_DENSITY), default=True): cv.boolean,
        vol.Optional(k(ATTR_ALIGN)): _ALIGN,
        vol.Optional(k(ATTR_IMAGE_WIDTH)): vol.All(
            vol.Coerce(int), vol.Range(min=IMAGE_WIDTH_MIN, max=IMAGE_WIDTH_MAX)
        ),
        vol.Optional(k(ATTR_ROTATION), default=0): vol.All(
            vol.Coerce(int), vol.In(ROTATION_VALUES)
        ),
        vol.Optional(k(ATTR_DITHER), default=DEFAULT_DITHER): vol.In(DITHER_MODES),
        vol.Optional(k(ATTR_THRESHOLD), default=DEFAULT_THRESHOLD): vol.All(
            vol.Coerce(int),
            vol.Range(min=IMAGE_THRESHOLD_MIN, max=IMAGE_THRESHOLD_MAX),
        ),
        vol.Optional(k(ATTR_IMPL)): vol.In(IMPL_MODES),
        vol.Optional(k(ATTR_CENTER), default=False): cv.boolean,
        vol.Optional(k(ATTR_AUTOCONTRAST), default=autocontrast): cv.boolean,
        vol.Optional(k(ATTR_INVERT), default=False): cv.boolean,
        vol.Optional(k(ATTR_MIRROR), default=False): cv.boolean,
        vol.Optional(k(ATTR_AUTO_RESIZE), default=auto_resize): cv.boolean,
        vol.Optional(k(ATTR_FALLBACK_IMAGE)): _IMAGE_SOURCE,
        vol.Optional(k(ATTR_FRAGMENT_HEIGHT)): vol.All(
            vol.Coerce(int),
            vol.Range(min=IMAGE_FRAGMENT_MIN, max=IMAGE_FRAGMENT_MAX),
        ),
        vol.Optional(k(ATTR_CHUNK_DELAY_MS)): vol.All(
            vol.Coerce(int),
            vol.Range(min=IMAGE_CHUNK_DELAY_MIN, max=IMAGE_CHUNK_DELAY_MAX),
        ),
    }


# M4: freeze the module-cached fragments with MappingProxyType. Voluptuous
# spreads these via ``**fragment`` so it never mutates them, but the
# read-only view makes the invariant explicit and refuses any future
# fixture that tries to add/override keys directly.
_IMAGE_OPTION_FRAGMENT_PLAIN = MappingProxyType(_image_option_fragment())
_IMAGE_OPTION_FRAGMENT_URL = MappingProxyType(_image_option_fragment(auto_resize=True))
_IMAGE_OPTION_FRAGMENT_CAMERA = MappingProxyType(
    _image_option_fragment(autocontrast=True, auto_resize=True)
)
_IMAGE_OPTION_FRAGMENT_NOTIFY = MappingProxyType(
    {
        vol.Optional(ATTR_IMAGE): _IMAGE_SOURCE,
        **_image_option_fragment("image_"),
    }
)


def _image_pipeline_knobs(prefix: str = "") -> dict[Any, Any]:
    """Pipeline-only knobs (dither/threshold/impl/rotation/...) without ``fallback_image``.

    Services that *produce* their own image bytes (currently
    ``print_text_image``) need the downstream pipeline parameters but
    have no source-image to fall back from. Sharing the full
    :func:`_image_option_fragment` would silently expose
    ``fallback_image`` — a field that is meaningless in that context
    and is not advertised in ``services.yaml`` — to programmatic
    callers, broadening the parity-invariant contract documented in
    ``CLAUDE.md``.

    ``prefix`` is forwarded so the caller can disambiguate the bare
    image keys (``dither``, ``invert``, …) from the surrounding service
    options. ``print_text_image`` uses ``"image_"`` so its UI fields
    line up with ``print_message``'s ``image_*`` knobs.
    """
    fallback_key = f"{prefix}{ATTR_FALLBACK_IMAGE}" if prefix else ATTR_FALLBACK_IMAGE
    return {
        k: v
        for k, v in _image_option_fragment(prefix).items()
        if not (isinstance(k, vol.Optional) and k.schema == fallback_key)
    }


PRINT_TEXT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_BOLD): cv.boolean,
        vol.Optional(ATTR_UNDERLINE): _UNDERLINE,
        vol.Optional(ATTR_WIDTH): _TEXT_SIZE,
        vol.Optional(ATTR_HEIGHT): _TEXT_SIZE,
        vol.Optional(ATTR_ENCODING): cv.string,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


PRINT_TEXT_UTF8_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_BOLD): cv.boolean,
        vol.Optional(ATTR_UNDERLINE): _UNDERLINE,
        vol.Optional(ATTR_WIDTH): _TEXT_SIZE,
        vol.Optional(ATTR_HEIGHT): _TEXT_SIZE,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


PRINT_QR_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_DATA): vol.All(cv.string, vol.Length(min=1, max=MAX_QR_DATA_LENGTH)),
        vol.Optional(ATTR_SIZE): vol.All(vol.Coerce(int), vol.Range(min=1, max=16)),
        vol.Optional(ATTR_EC): vol.In(["L", "M", "Q", "H"]),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


_PRINT_IMAGE_SCHEMA_DICT: dict[Any, Any] = {
    vol.Optional("device_id"): _DEVICE_ID,
    vol.Required(ATTR_IMAGE): _IMAGE_SOURCE,
    **_IMAGE_OPTION_FRAGMENT_PLAIN,
    vol.Optional(ATTR_CUT): _CUT,
    vol.Optional(ATTR_FEED): _FEED,
}
PRINT_IMAGE_SCHEMA = vol.Schema(_PRINT_IMAGE_SCHEMA_DICT)


# Focused convenience-service schemas — the source field constrains the
# selector to a single domain, so the UI can present an entity picker
# instead of the generic template selector. Internally these all funnel
# into the same ``handle_print_image`` logic.
def _entity_id_in_domain(domain: str):  # type: ignore[no-untyped-def]
    def _validate(value: Any) -> str:
        if not isinstance(value, str):
            raise vol.Invalid(f"{domain} entity must be a string")
        if not value.startswith(f"{domain}."):
            raise vol.Invalid(f"Expected entity_id in domain '{domain}'")
        return value

    return _validate


# Per-service source-type guards. Each focused service advertises a
# specific source shape (URL / local path) in its description; without
# these guards the underlying ``_classify()`` would happily route a
# wrong-shape value through a different resolver, contradicting the
# advertised contract. Downstream guards (SSRF, allowlist, O_NOFOLLOW,
# entity ACL) still apply — these are defense-in-depth so the schema
# matches the documented intent.
def _url_only(value: Any) -> str:
    s = cv.string(value)
    if not s.lower().startswith(("http://", "https://")):
        raise vol.Invalid("URL must start with http:// or https://")
    return s


def _local_path_only(value: Any) -> str:
    s = cv.string(value)
    if s.lower().startswith(("http://", "https://", "data:", "camera.", "image.")):
        raise vol.Invalid("Path must be a local filesystem path")
    return s


# The focused services advertise a friendly feed default in services.yaml
# (a small paper buffer so a one-off print tears off cleanly). Set the
# same default in the schema so a YAML/script caller that omits ``feed``
# gets the advertised behaviour instead of 0 — without the schema default
# voluptuous never injects the key and the handler's
# ``call.data.get(ATTR_FEED)`` returns None (→ 0 lines). The generic
# ``print_image`` keeps no default (services.yaml advertises 0).
PRINT_CAMERA_SNAPSHOT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("camera_entity"): _entity_id_in_domain("camera"),
        **_IMAGE_OPTION_FRAGMENT_CAMERA,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED, default=2): _FEED,
    }
)

PRINT_IMAGE_ENTITY_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("image_entity"): _entity_id_in_domain("image"),
        **_IMAGE_OPTION_FRAGMENT_PLAIN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED, default=1): _FEED,
    }
)

PRINT_IMAGE_URL_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("url"): vol.All(_url_only, vol.Length(min=1, max=MAX_URL_LENGTH)),
        **_IMAGE_OPTION_FRAGMENT_URL,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED, default=1): _FEED,
    }
)

PRINT_IMAGE_PATH_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required("path"): vol.All(
            _local_path_only, vol.Length(min=1, max=MAX_IMAGE_PATH_LENGTH)
        ),
        **_IMAGE_OPTION_FRAGMENT_URL,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED, default=1): _FEED,
    }
)

PREVIEW_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_IMAGE): _IMAGE_SOURCE,
        vol.Optional("output_path"): cv.string,
        **_IMAGE_OPTION_FRAGMENT_PLAIN,
    }
)

CALIBRATION_PRINT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Optional(ATTR_CUT, default="full"): _CUT,
        vol.Optional(ATTR_FEED, default=2): _FEED,
    }
)


_BORDER_STYLE = vol.In(sorted(BORDER_STYLES))


def _validate_rows_shape(value: Any) -> list[list[Any]]:
    """Schema-level shape check for ``print_table.rows``.

    The deeper per-cell sanitisation lives in
    :func:`..security.validate_rows` (called by the handler so the
    sanitised result feeds the renderer). Here we only enforce list-of-
    lists structure plus the row/column count bounds so a malformed
    payload fails fast at the service-registry layer.
    """
    if not isinstance(value, list):
        raise vol.Invalid("rows must be a list of rows")
    if not value:
        raise vol.Invalid("rows must contain at least one row")
    if len(value) > MAX_TABLE_ROWS:
        raise vol.Invalid(f"rows length {len(value)} exceeds maximum {MAX_TABLE_ROWS}")
    out: list[list[Any]] = []
    for row in value:
        if not isinstance(row, list):
            raise vol.Invalid("each row must be a list")
        if len(row) > MAX_TABLE_COLS:
            raise vol.Invalid(f"row width {len(row)} exceeds maximum {MAX_TABLE_COLS}")
        out.append(row)
    return out


def _validate_column_aligns(value: Any) -> list[str]:
    """Schema-level check for ``print_table.column_aligns``.

    Mirrors :func:`_validate_rows_shape` — keeps the per-element
    enumeration in the schema layer so REST/script callers fail fast
    before the handler runs.
    """
    if not isinstance(value, list):
        raise vol.Invalid("column_aligns must be a list of strings")
    out: list[str] = []
    for v in value:
        if v not in ("left", "center", "right"):
            raise vol.Invalid(f"column align must be left/center/right; got {v!r}")
        out.append(str(v))
    return out


def _validate_column_widths(value: Any) -> list[int]:
    """Schema-level check for ``print_table.column_widths``.

    Bounds each width to ``1..MAX_BOX_WIDTH`` and the list length to
    ``MAX_TABLE_COLS`` so a malformed payload is rejected at the
    service-registry layer rather than deep in the renderer.
    """
    if not isinstance(value, list):
        raise vol.Invalid("column_widths must be a list of integers")
    if len(value) > MAX_TABLE_COLS:
        raise vol.Invalid(f"column_widths length {len(value)} exceeds maximum {MAX_TABLE_COLS}")
    out: list[int] = []
    for v in value:
        try:
            iv = int(v)
        except (TypeError, ValueError) as exc:
            raise vol.Invalid(f"column width must be an integer; got {v!r}") from exc
        if not 1 <= iv <= MAX_BOX_WIDTH:
            raise vol.Invalid(f"column width {iv} out of range 1..{MAX_BOX_WIDTH}")
        out.append(iv)
    return out


PRINT_BOX_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_STYLE, default=DEFAULT_BORDER_STYLE): _BORDER_STYLE,
        vol.Optional(ATTR_PADDING, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
        vol.Optional(ATTR_ALIGN, default="left"): _ALIGN,
        vol.Optional(ATTR_TOTAL_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=MAX_BOX_WIDTH)
        ),
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


PRINT_TABLE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_ROWS): _validate_rows_shape,
        vol.Optional(ATTR_STYLE, default=DEFAULT_BORDER_STYLE): _BORDER_STYLE,
        vol.Optional(ATTR_COLUMN_WIDTHS): _validate_column_widths,
        vol.Optional(ATTR_COLUMN_ALIGNS): _validate_column_aligns,
        vol.Optional(ATTR_HEADER, default=False): cv.boolean,
        vol.Optional(ATTR_ROW_SEPARATORS, default=False): cv.boolean,
        vol.Optional(ATTR_TOTAL_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=MAX_BOX_WIDTH)
        ),
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


def _validate_separator_char(value: Any) -> str:
    """Validate a single printable-ASCII character for ``print_separator``.

    Multi-char strings, empty strings, and control characters are
    rejected here rather than in the handler so REST/script callers get
    the same fast feedback as the UI selector.
    """
    if not isinstance(value, str):
        raise vol.Invalid(f"char must be a string; got {type(value).__name__}")
    if len(value) != 1:
        raise vol.Invalid(f"char must be exactly one character; got {value!r}")
    code = ord(value)
    if not 0x20 <= code <= 0x7E:
        raise vol.Invalid("char must be a printable ASCII character (0x20-0x7E)")
    return value


PRINT_SEPARATOR_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Optional(ATTR_CHAR, default="-"): _validate_separator_char,
        vol.Optional(ATTR_WIDTH): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_BOX_WIDTH)),
        vol.Optional(ATTR_REPEAT, default=1): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_SEPARATOR_REPEAT)
        ),
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


def _validate_kv_items(value: Any) -> list[list[Any]]:
    """Schema-level shape check for ``print_kvtable.items`` (P-H1).

    Runs on the event loop, so this is intentionally shape-only:
    ``items`` is a non-empty list of 2-element lists, each cell
    bounded by ``MAX_TABLE_CELL_LENGTH``. The per-cell control-char
    strip + ``str`` coercion lives in
    :func:`..security.sanitise_kv_items`, dispatched to the executor
    by the handler so per-cell regex work does not block the loop.
    """
    if not isinstance(value, list):
        raise vol.Invalid("items must be a list of [label, value] pairs")
    if not value:
        raise vol.Invalid("items must contain at least one entry")
    if len(value) > MAX_TABLE_ROWS:
        raise vol.Invalid(f"items length {len(value)} exceeds maximum {MAX_TABLE_ROWS}")
    out: list[list[Any]] = []
    for entry in value:
        if not isinstance(entry, list) or len(entry) != 2:
            raise vol.Invalid("each item must be a 2-element [label, value] list")
        for cell in entry:
            if cell is not None:
                s = str(cell)
                if len(s) > MAX_TABLE_CELL_LENGTH:
                    raise vol.Invalid(
                        f"cell length {len(s)} exceeds maximum {MAX_TABLE_CELL_LENGTH}"
                    )
        out.append(entry)
    return out


PRINT_KVTABLE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_ITEMS): _validate_kv_items,
        vol.Optional(ATTR_STYLE, default="none"): _BORDER_STYLE,
        vol.Optional(ATTR_TOTAL_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=MAX_BOX_WIDTH)
        ),
        vol.Optional(ATTR_LABEL_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_BOX_WIDTH)
        ),
        vol.Optional(ATTR_VALUE_ALIGN, default="right"): _ALIGN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


PREVIEW_BOX_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_STYLE, default=DEFAULT_BORDER_STYLE): _BORDER_STYLE,
        vol.Optional(ATTR_PADDING, default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=4)),
        vol.Optional(ATTR_ALIGN, default="left"): _ALIGN,
        vol.Optional(ATTR_TOTAL_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=MAX_BOX_WIDTH)
        ),
        vol.Optional(ATTR_OUTPUT_PATH): cv.string,
    }
)


PREVIEW_TABLE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_ROWS): _validate_rows_shape,
        vol.Optional(ATTR_STYLE, default=DEFAULT_BORDER_STYLE): _BORDER_STYLE,
        vol.Optional(ATTR_COLUMN_WIDTHS): _validate_column_widths,
        vol.Optional(ATTR_COLUMN_ALIGNS): _validate_column_aligns,
        vol.Optional(ATTR_HEADER, default=False): cv.boolean,
        vol.Optional(ATTR_ROW_SEPARATORS, default=False): cv.boolean,
        vol.Optional(ATTR_TOTAL_WIDTH): vol.All(
            vol.Coerce(int), vol.Range(min=3, max=MAX_BOX_WIDTH)
        ),
        vol.Optional(ATTR_OUTPUT_PATH): cv.string,
    }
)


# Reuse the image-pipeline knobs so the rendered PNG flows through the
# same dither / threshold / slice path as ``print_image``. The fragment
# already carries ``rotation`` (0/90/180/270) — the text-side handler
# applies it to the PIL canvas BEFORE binarisation, so the user-facing
# meaning ("rotate the text") matches.
PRINT_TEXT_IMAGE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_TEXT): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
        vol.Optional(ATTR_FONT_NAME, default=DEFAULT_FONT_NAME): vol.In(
            sorted(BUILTIN_FONT_CHOICES)
        ),
        vol.Optional(ATTR_FONT_PATH): vol.All(
            cv.string, vol.Length(min=1, max=MAX_FONT_PATH_LENGTH)
        ),
        vol.Optional(ATTR_FONT_SIZE, default=DEFAULT_FONT_SIZE): vol.All(
            vol.Coerce(int), vol.Range(min=8, max=MAX_FONT_SIZE_PT)
        ),
        vol.Optional(ATTR_LINE_SPACING, default=DEFAULT_LINE_SPACING): vol.All(
            vol.Coerce(float), vol.Range(min=1.0, max=3.0)
        ),
        # Text-canvas controls: applied to the PIL canvas before binarisation,
        # so the printed orientation/alignment matches what the user typed.
        # The image-side ``image_rotation`` is forced to 0 at dispatch.
        vol.Optional(ATTR_ALIGN, default="left"): _ALIGN,
        vol.Optional(ATTR_ROTATION, default=0): vol.All(vol.Coerce(int), vol.In(ROTATION_VALUES)),
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
        # Pipeline knobs prefixed with ``image_`` so the UI fields line up
        # one-to-one with ``print_message``'s ``image_*`` knobs.
        # ``fallback_image`` is intentionally excluded because this service
        # renders its own bytes (see :func:`_image_pipeline_knobs`).
        **_image_pipeline_knobs("image_"),
    }
)


PRINT_BARCODE_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_CODE): vol.All(cv.string, vol.Length(min=1, max=MAX_BARCODE_LENGTH)),
        vol.Required(ATTR_BC): cv.string,
        vol.Optional(ATTR_BARCODE_HEIGHT): vol.All(vol.Coerce(int), vol.Range(min=1, max=255)),
        vol.Optional(ATTR_BARCODE_WIDTH): vol.All(vol.Coerce(int), vol.Range(min=2, max=6)),
        vol.Optional(ATTR_POS): vol.In(["ABOVE", "BELOW", "BOTH", "OFF"]),
        vol.Optional(ATTR_FONT): vol.In(["A", "B"]),
        vol.Optional(ATTR_ALIGN_CT): cv.boolean,
        vol.Optional(ATTR_CHECK): cv.boolean,
        # ``force_software`` accepts bool, "true"/"false" strings, and the
        # python-escpos impl names ("graphics", "bitImageColumn",
        # "bitImageRaster"). The handler does the cleanup; here we only
        # restrict the shape.
        vol.Optional(ATTR_FORCE_SOFTWARE): vol.Any(
            cv.boolean,
            vol.In(["graphics", "bitImageColumn", "bitImageRaster"]),
        ),
        vol.Optional(ATTR_ALIGN): _ALIGN,
        vol.Optional(ATTR_CUT): _CUT,
        vol.Optional(ATTR_FEED): _FEED,
    }
)


FEED_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_LINES): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_FEED_LINES)),
    }
)


CUT_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Required(ATTR_MODE): vol.In(["full", "partial"]),
    }
)


BEEP_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): _DEVICE_ID,
        vol.Optional(ATTR_TIMES): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
        vol.Optional(ATTR_DURATION): vol.All(vol.Coerce(int), vol.Range(min=1, max=10)),
    }
)


# Schema for the notify entity's `print_message` action. Wrapped in
# `cv.make_entity_service_schema` by the notify platform itself, so we
# only export the inner dict here.
PRINT_MESSAGE_FIELDS: dict[Any, Any] = {
    vol.Required(ATTR_MESSAGE): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
    vol.Optional(ATTR_TITLE): vol.All(cv.string, vol.Length(max=MAX_TEXT_LENGTH)),
    vol.Optional("align"): _ALIGN,
    vol.Optional("bold"): cv.boolean,
    vol.Optional("underline"): _UNDERLINE,
    vol.Optional("width"): _TEXT_SIZE,
    vol.Optional("height"): _TEXT_SIZE,
    vol.Optional("utf8"): cv.boolean,
    vol.Optional("encoding"): cv.string,
    vol.Optional("cut"): _CUT,
    vol.Optional("feed"): _FEED,
    **_IMAGE_OPTION_FRAGMENT_NOTIFY,
}


__all__ = [
    "BEEP_SCHEMA",
    "CALIBRATION_PRINT_SCHEMA",
    "CUT_SCHEMA",
    "FEED_SCHEMA",
    "PREVIEW_BOX_SCHEMA",
    "PREVIEW_IMAGE_SCHEMA",
    "PREVIEW_TABLE_SCHEMA",
    "PRINT_BARCODE_SCHEMA",
    "PRINT_BOX_SCHEMA",
    "PRINT_CAMERA_SNAPSHOT_SCHEMA",
    "PRINT_IMAGE_ENTITY_SCHEMA",
    "PRINT_IMAGE_PATH_SCHEMA",
    "PRINT_IMAGE_SCHEMA",
    "PRINT_IMAGE_URL_SCHEMA",
    "PRINT_KVTABLE_SCHEMA",
    "PRINT_MESSAGE_FIELDS",
    "PRINT_QR_SCHEMA",
    "PRINT_SEPARATOR_SCHEMA",
    "PRINT_TABLE_SCHEMA",
    "PRINT_TEXT_IMAGE_SCHEMA",
    "PRINT_TEXT_SCHEMA",
    "PRINT_TEXT_UTF8_SCHEMA",
]
