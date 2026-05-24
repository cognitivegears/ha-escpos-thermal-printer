"""Security utilities for the ESC/POS Thermal Printer integration.

This module is the single source of truth for input validation, log
sanitization, and the numeric bounds shared between ``services.yaml``,
the voluptuous schemas, and the adapter-level validators.

Functions here are deliberately split into two flavors:

- Synchronous validators (cheap CPU / string work) — safe on the event loop.
- ``*_async`` wrappers (DNS resolution, filesystem stat, file open) — must
  be awaited from the event loop; they hop to an executor internally.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import logging
import os
from pathlib import Path
import re
import socket
import stat
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from .const import DITHER_MODES, IMPL_MODES, ROTATION_VALUES

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bounds & limits (single source of truth — reused by voluptuous schemas,
# the adapter's belt-and-braces validators, and `services.yaml` selectors).
# ---------------------------------------------------------------------------

MAX_TEXT_LENGTH = 10000  # Maximum text length to prevent resource exhaustion
MAX_QR_DATA_LENGTH = 2000  # Maximum QR code data length
MAX_BARCODE_LENGTH = 100  # Maximum barcode data length
MAX_IMAGE_SIZE_MB = 10  # Maximum image download / decoded size, MB
MAX_FEED_LINES = 50  # Maximum feed lines to prevent paper waste
MAX_BEEP_TIMES = 10  # Maximum beep repetitions
# B-L2: separate semantic bound for beep *duration*. Numerically the same
# upper bound today, but the schema + validators should not pretend the
# two fields share a meaning. Units are python-escpos "buzzer ticks"
# (~100ms per tick on most supported printers).
MAX_BEEP_DURATION = 10

# Image processing bounds (mirror in `services.yaml` + voluptuous schemas).
IMAGE_WIDTH_MIN = 16
IMAGE_WIDTH_MAX = 2048
IMAGE_THRESHOLD_MIN = 1
IMAGE_THRESHOLD_MAX = 254
IMAGE_FRAGMENT_MIN = 16
IMAGE_FRAGMENT_MAX = 1024
IMAGE_CHUNK_DELAY_MIN = 0
IMAGE_CHUNK_DELAY_MAX = 5000

# Maximum decoded pixel count for a single image. Set process-globally on
# ``PIL.Image.MAX_IMAGE_PIXELS`` by ``image_processor`` so PIL's bomb
# protection fires deterministically.
MAX_IMAGE_PIXELS = 20_000_000

# Post-processing height (rows) and per-print slice count caps. Both
# protect against paper-waste DoS (legitimate receipts rarely exceed
# either limit; an attacker can otherwise burn the entire roll).
MAX_PROCESSED_HEIGHT = 8192
MAX_SLICES = 64

# URL validation
VALID_URL_SCHEMES = frozenset({"http", "https"})
VALID_URL_PORTS = frozenset({None, 80, 443})
MAX_URL_LENGTH = 2000  # de-facto browser/proxy URL-length safe limit (≈ RFC 7230 §3.1.1 folklore)

# Local file path validation. POSIX PATH_MAX is 4096 on Linux; 1024 is
# conservative and covers every legitimate HA path universe (/config,
# /media, Supervisor bind mounts) by a wide margin.
MAX_IMAGE_PATH_LENGTH = 1024

# Local file validation. HEIC/HEIF/AVIF are accepted when ``pillow-heif``
# is installed (see ``printer/image_processor._register_heif_opener``).
# The allowlist is the union of every format we *might* be able to
# decode — Pillow's ``formats=`` parameter in the actual decode step is
# the real gate, so listing them here without the opener is a no-op.
VALID_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp", ".heic", ".heif", ".avif"}
)

# Text-effects bounds. ``MAX_BOX_WIDTH`` is generous (covers 80-column
# wide-receipt printers) and ``MAX_TABLE_*`` keeps a single service call
# from blowing the paper budget. ``MAX_FONT_SIZE_PT`` caps the rendered
# image height — at 72-DPI a 96-pt font is already ~130 px tall per
# line, well above what a 384-px-wide receipt printer can show
# legibly.
MAX_BOX_WIDTH = 200
MAX_TABLE_ROWS = 200
MAX_TABLE_COLS = 12
MAX_TABLE_CELL_LENGTH = 1000
# Maximum consecutive separator lines a single ``print_separator`` call
# may emit. Ten lines is already a heavy decorative block; this cap
# stops a runaway automation from consuming a whole receipt of paper.
MAX_SEPARATOR_REPEAT = 10
MAX_FONT_SIZE_PT = 96
MAX_FONT_PATH_LENGTH = MAX_IMAGE_PATH_LENGTH
ALLOWED_FONT_EXTENSIONS = frozenset({".ttf", ".otf"})

# Maximum size of a user-supplied TTF/OTF file. Real-world fonts top out
# in the low-MB range (DejaVuSans is ~740 KB); 16 MB is generous and
# prevents an attacker-supplied multi-GB file from pinning FreeType's
# parser in tens of seconds of allocation work.
MAX_FONT_SIZE_BYTES = 16 * 1024 * 1024

# Cap on the rendered text-image canvas. ``MAX_RENDER_HEIGHT_PX`` is the
# pre-rotation height ceiling — chosen to match ``MAX_PROCESSED_HEIGHT``
# so a canvas that passes here cannot stall the downstream slice
# pipeline. ``MAX_RENDER_PIXELS`` is a belt-and-braces total-area cap
# against any rotation/expand explosion that doubles memory.
MAX_RENDER_HEIGHT_PX = MAX_PROCESSED_HEIGHT  # 8192
MAX_RENDER_PIXELS = 5_000_000  # ~5 MP — well above any legitimate receipt

# B-L5: pin the invariant. The text-image renderer (``text_effects.font_render``)
# uses ``MAX_RENDER_HEIGHT_PX`` to reject canvases the downstream slicer
# (``image_processor``) couldn't handle anyway. If a future change splits
# the two, the renderer could produce a canvas the slicer immediately
# rejects.
assert MAX_RENDER_HEIGHT_PX <= MAX_PROCESSED_HEIGHT, (
    "MAX_RENDER_HEIGHT_PX must not exceed MAX_PROCESSED_HEIGHT — the "
    "renderer's height cap must stay <= the slicer's height cap so a "
    "canvas that passes here cannot stall the slice pipeline."
)

# Permitted data-URI subtypes. Pinned so a future regression can't
# accidentally enable SVG (no Pillow renderer; cairo-based fallbacks are
# an XML attack surface). HEIC/HEIF/AVIF added so iOS / drone-style
# camera proxies can paste snapshots inline.
_DATA_URI_RE = re.compile(
    r"^data:image/(?P<subtype>png|jpe?g|gif|bmp|tiff|webp|heic|heif|avif);base64,"
    r"(?P<data>[A-Za-z0-9+/=\s]+)$"
)

# Maximum input size for a base64 data URI before we even attempt to
# regex-match or decode. base64 expands 3 bytes -> 4 chars, so a 10 MB
# decoded payload is roughly 13.4 MB of base64; add headroom for the
# ``data:image/...;base64,`` prefix.
MAX_BASE64_INPUT_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024 * 4 // 3 + 256

# Maximum length of an entity_id object-id segment (the part after the dot).
# Anchors the regex so an attacker can't hand us a megabyte string to
# burn CPU on.
MAX_ENTITY_ID_OBJECT_LEN = 64


def validate_text_input(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Validate and sanitize printable-text input."""
    if not isinstance(text, str):
        raise HomeAssistantError("Text input must be a string")

    if len(text) > max_length:
        raise HomeAssistantError(f"Text length exceeds maximum of {max_length} characters")

    # Strip C0 control characters except CR/LF/HT (which ESC/POS handles).
    sanitized = _CONTROL_CHAR_RE.sub("", text)

    if len(sanitized) != len(text):
        _LOGGER.warning("Text input contained control characters that were removed")

    return sanitized


def validate_qr_data(data: str) -> str:
    """Validate QR code data."""
    if not isinstance(data, str):
        raise HomeAssistantError("QR data must be a string")

    if len(data) > MAX_QR_DATA_LENGTH:
        raise HomeAssistantError(
            f"QR data length exceeds maximum of {MAX_QR_DATA_LENGTH} characters"
        )

    if not data.strip():
        raise HomeAssistantError("QR data cannot be empty")

    return data


def validate_barcode_data(code: str, bc_type: str) -> tuple[str, str]:
    """Validate barcode data + type and normalize aliases."""
    if not isinstance(code, str) or not isinstance(bc_type, str):
        raise HomeAssistantError("Barcode code and type must be strings")

    if len(code) > MAX_BARCODE_LENGTH:
        raise HomeAssistantError(
            f"Barcode data length exceeds maximum of {MAX_BARCODE_LENGTH} characters"
        )

    if not code.strip():
        raise HomeAssistantError("Barcode data cannot be empty")

    aliases = {
        "UPC-A": "UPCA",
        "UPC": "UPCA",
        "NW7": "CODABAR",
        "JAN": "EAN13",
        "JAN13": "EAN13",
        "JAN8": "EAN8",
    }
    valid_types = {
        "EAN13",
        "EAN8",
        "UPCA",
        "UPC-A",
        "UPC-E",
        "CODE39",
        "CODE93",
        "CODE128",
        "ITF",
        "ITF14",
        "CODABAR",
        "NW7",
        "JAN",
        "JAN13",
        "JAN8",
    }
    bc_upper = bc_type.upper()
    if bc_upper not in valid_types:
        _LOGGER.warning("Unknown barcode type '%s', proceeding with caution", bc_type)
    bc_canonical = aliases.get(bc_upper, bc_upper)
    return code, bc_canonical


# ---------------------------------------------------------------------------
# URL validation (SSRF-aware).
# ---------------------------------------------------------------------------


def validate_image_url(url: str) -> str:
    """Cheap synchronous URL validation.

    Rejects URLs that are structurally bad (wrong scheme, no hostname, too
    long, contain credentials, use non-default ports, contain IDN
    punycode). Does **not** resolve DNS — use
    :func:`validate_image_url_and_resolve` from the event loop to also
    check the resolved address is public.
    """
    if not isinstance(url, str):
        raise HomeAssistantError("Image URL must be a string")

    if len(url) > MAX_URL_LENGTH:
        raise HomeAssistantError("URL is too long")

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise HomeAssistantError(f"Invalid URL format: {exc}") from exc

    if parsed.scheme not in VALID_URL_SCHEMES:
        raise HomeAssistantError(
            f"Invalid URL scheme. Only {sorted(VALID_URL_SCHEMES)} are allowed"
        )

    if not parsed.hostname:
        raise HomeAssistantError("URL must include a valid hostname")

    if parsed.username or parsed.password:
        raise HomeAssistantError("URLs with embedded credentials are not allowed")

    # IDN/punycode: a homograph URL renders visually identical to a
    # legitimate one in logs/toasts. Reject IDN hostnames whether the
    # caller sent them as raw Unicode (``例え.テスト``) or pre-encoded
    # (``xn--r8jz45g.xn--zckzah``). S-M6: the previous substring check
    # missed raw-Unicode input because ``urlparse`` does not IDNA-encode
    # for us — ``parsed.hostname`` for ``例え.テスト`` is the literal
    # string, not ``xn--``-prefixed. Encode-then-check catches both.
    hostname_to_check = parsed.hostname
    if any(ord(c) > 0x7F for c in hostname_to_check):
        try:
            hostname_to_check = hostname_to_check.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise HomeAssistantError(f"Invalid IDN hostname: {exc}") from exc
    if "xn--" in hostname_to_check.lower():
        raise HomeAssistantError(
            "Internationalized (IDN/punycode) hostnames are not allowed; "
            "use the ASCII hostname or a numeric IP to avoid homograph confusion."
        )

    # Restrict to default ports for the scheme. Catches both 22 (SSH) and
    # 8123 (HA itself).
    if parsed.port not in VALID_URL_PORTS:
        raise HomeAssistantError(
            f"URL port {parsed.port} not allowed; only {sorted(p for p in VALID_URL_PORTS if p)} are permitted"
        )

    return url


def _is_public_address(addr: str) -> bool:
    """Return True if ``addr`` is a globally routable IP address."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _resolve_hostname_sync(hostname: str, port: int | None) -> list[str]:
    """Resolve ``hostname`` to a list of IP literals; raise on failure."""
    try:
        infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise HomeAssistantError(f"Could not resolve image URL hostname: {exc}") from exc
    addrs = sorted({str(info[4][0]) for info in infos})
    if not addrs:
        raise HomeAssistantError("Could not resolve image URL hostname")
    return addrs


async def validate_image_url_and_resolve(hass: HomeAssistant, url: str) -> tuple[str, list[str]]:
    """Validate ``url`` and resolve its hostname, rejecting private targets.

    Returns ``(validated_url, resolved_addresses)``. The caller should pin
    one of the resolved addresses for the actual fetch (defeats DNS
    rebinding); see ``image_sources._resolve_http``.
    """
    validated = validate_image_url(url)
    parsed = urlparse(validated)
    hostname = parsed.hostname
    if hostname is None:  # pragma: no cover — validate_image_url enforces it
        raise HomeAssistantError("URL must include a valid hostname")
    addrs = await hass.async_add_executor_job(_resolve_hostname_sync, hostname, parsed.port)
    bad = [a for a in addrs if not _is_public_address(a)]
    if bad:
        raise HomeAssistantError(
            "Image URL resolves to a non-public address "
            "(private, loopback, link-local, reserved, or multicast)"
        )
    return validated, addrs


# ---------------------------------------------------------------------------
# Local-file validation.
# ---------------------------------------------------------------------------


def _validate_local_path_sync(
    raw_path: str,
    allowed: frozenset[str] = VALID_IMAGE_EXTENSIONS,
    *,
    max_bytes: int | None = None,
) -> Path:
    """Resolve and validate a local image path.

    Returns the resolved ``Path`` (symlinks dereferenced). Raises
    :class:`HomeAssistantError` on any failure. Blocking — call from an
    executor thread only.

    ``max_bytes`` lets callers raise the per-file cap when ``auto_resize``
    is set (the decoded image will be downscaled before the pixel-count
    cap fires).
    """
    if not isinstance(raw_path, str):
        raise HomeAssistantError("Image path must be a string")

    if max_bytes is None:
        max_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024

    try:
        resolved = Path(raw_path).resolve(strict=True)
    except FileNotFoundError as exc:
        raise HomeAssistantError("Image file does not exist or is not a regular file") from exc
    except OSError as exc:
        raise HomeAssistantError(f"Cannot access image file: {exc}") from exc

    if resolved.suffix.lower() not in allowed:
        raise HomeAssistantError(
            f"File extension '{resolved.suffix}' not allowed. Allowed: {sorted(allowed)}"
        )

    try:
        st = resolved.stat()
    except OSError as exc:
        raise HomeAssistantError(f"Cannot access image file: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise HomeAssistantError("Image path is not a regular file")
    if st.st_size > max_bytes:
        mb = max_bytes // (1024 * 1024)
        raise HomeAssistantError(f"Image file too large (max {mb}MB)")

    return resolved


def validate_font_path(
    raw_path: str,
    *,
    hass: HomeAssistant | None = None,
) -> Path:
    """Resolve and validate a user-supplied font path.

    Mirrors :func:`_validate_local_path_sync` but for ``.ttf`` / ``.otf``
    files and without the per-file size cap (font files are routinely
    in the multi-megabyte range). The user-supplied path itself must
    not be a symlink (``Path.is_symlink``) — this defeats the "drop a
    symlink in ``<config>/fonts/`` pointing at ``/etc/...``" trick
    that would otherwise let an attacker make Pillow parse arbitrary
    on-disk binaries. The resolved path is then rejected if it falls
    outside ``hass``'s ``allowlist_external_dirs`` (when ``hass`` is
    supplied — the standalone form is used by unit tests).

    Blocking — call from an executor thread when ``hass`` is set,
    because ``hass.config.is_allowed_path`` may stat the filesystem.
    """
    if not isinstance(raw_path, str):
        raise HomeAssistantError("Font path must be a string")
    if len(raw_path) > MAX_FONT_PATH_LENGTH:
        raise HomeAssistantError(f"Font path exceeds maximum length {MAX_FONT_PATH_LENGTH}")
    try:
        raw_is_symlink = Path(raw_path).is_symlink()
    except OSError as exc:
        raise HomeAssistantError(f"Cannot access font file: {exc}") from exc
    if raw_is_symlink:
        raise HomeAssistantError("Font path must not be a symlink")
    try:
        resolved = Path(raw_path).resolve(strict=True)
    except FileNotFoundError as exc:
        raise HomeAssistantError("Font file does not exist or is not a regular file") from exc
    except OSError as exc:
        raise HomeAssistantError(f"Cannot access font file: {exc}") from exc

    if resolved.suffix.lower() not in ALLOWED_FONT_EXTENSIONS:
        raise HomeAssistantError(
            f"Font extension '{resolved.suffix}' not allowed. "
            f"Allowed: {sorted(ALLOWED_FONT_EXTENSIONS)}"
        )

    try:
        st = resolved.stat()
    except OSError as exc:
        raise HomeAssistantError(f"Cannot access font file: {exc}") from exc
    if not stat.S_ISREG(st.st_mode):
        raise HomeAssistantError("Font path is not a regular file")
    if st.st_size > MAX_FONT_SIZE_BYTES:
        mb = MAX_FONT_SIZE_BYTES // (1024 * 1024)
        raise HomeAssistantError(f"Font file too large (max {mb}MB)")

    if hass is not None and not hass.config.is_allowed_path(str(resolved)):
        raise HomeAssistantError(f"Font path '{resolved}' is outside allowlist_external_dirs")

    return resolved


def validate_font_path_with_fonts_dir(raw_path: str, hass: HomeAssistant) -> Path:
    """Validate a font path, accepting ``<config>/fonts/`` in addition to allowlist.

    Single entrypoint for the ``print_text_image`` handler (S-M1: trust
    decision moved here from ``services/print_handlers._is_font_path_allowed``
    so all path-validation policy lives next to ``validate_font_path``).

    The narrowing — only one well-known subdirectory of the HA config
    dir, only for font loading — keeps HA's broader allowlist model
    intact for other path-based services. Blocking; call from an
    executor thread.
    """
    # Run extension / size / symlink / regular-file checks first (these
    # don't depend on the allowlist decision).
    resolved = validate_font_path(raw_path)
    resolved_str = str(resolved)
    if hass.config.is_allowed_path(resolved_str):
        return resolved
    try:
        fonts_dir = Path(hass.config.path("fonts")).resolve()
    except (OSError, ValueError) as exc:
        raise HomeAssistantError(
            f"Font path '{resolved}' is outside allowlist_external_dirs "
            f"(and <config>/fonts/ is not accessible)"
        ) from exc
    try:
        if Path(resolved_str).resolve().is_relative_to(fonts_dir):
            return resolved
    except (OSError, ValueError) as exc:
        raise HomeAssistantError(
            f"Font path '{resolved}' is outside allowlist_external_dirs "
            f"(and not under <config>/fonts/)"
        ) from exc
    raise HomeAssistantError(
        f"Font path '{resolved}' is outside allowlist_external_dirs "
        f"(and not under <config>/fonts/)"
    )


# Combined control-character strip regex. Used by both `validate_text_input`
# and `_strip_controls` so the per-cell sanitisation path in `validate_rows`
# doesn't re-run isinstance + length checks for every cell (M5).
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _strip_controls(text: str) -> str:
    """Strip C0 control characters (except CR/LF/HT) from a known-str cell.

    Internal helper used inside ``validate_rows`` / ``sanitise_kv_items``
    where the caller already enforced ``isinstance(text, str)`` and the
    length cap. Mirrors the regex pass in :func:`validate_text_input`
    without the extra type / length re-checks (M5: ~2 ms saved per
    max-size table).
    """
    return _CONTROL_CHAR_RE.sub("", text)


def validate_rows(rows: Any) -> list[list[str]]:
    """Validate the ``rows`` argument of the print_table service.

    Enforces row/column/cell bounds and sanitizes every cell through
    the internal control-character stripper so the table renderer
    never sees C0 controls. Accepts any sequence-of-sequences;
    coerces non-string cells to ``str`` (mirroring the renderer's own
    coercion).
    """
    if not isinstance(rows, (list, tuple)):
        raise HomeAssistantError("rows must be a list of rows")
    if len(rows) > MAX_TABLE_ROWS:
        raise HomeAssistantError(f"rows length {len(rows)} exceeds maximum {MAX_TABLE_ROWS}")
    if not rows:
        raise HomeAssistantError("rows must contain at least one row")
    out: list[list[str]] = []
    for row in rows:
        if not isinstance(row, (list, tuple)):
            raise HomeAssistantError("each row must be a list of cells")
        if len(row) > MAX_TABLE_COLS:
            raise HomeAssistantError(f"row width {len(row)} exceeds maximum {MAX_TABLE_COLS}")
        cells: list[str] = []
        for cell in row:
            if cell is None:
                cells.append("")
                continue
            text = str(cell)
            if len(text) > MAX_TABLE_CELL_LENGTH:
                raise HomeAssistantError(f"cell length exceeds maximum {MAX_TABLE_CELL_LENGTH}")
            cells.append(_strip_controls(text))
        out.append(cells)
    return out


def sanitise_kv_items(items: Any) -> list[list[str]]:
    """Sanitise the ``items`` payload of ``print_kvtable``.

    Shape-checking lives in :func:`services.schemas._validate_kv_items_shape`
    (runs on the event loop — cheap). This function does the per-cell
    control-character strip on the executor (P-H1: per-cell regex work
    scales with payload size and shouldn't block the loop). The caller
    has already enforced 2-element lists and the per-cell length cap,
    so we coerce and strip without re-checking shape.
    """
    out: list[list[str]] = []
    for entry in items:
        pair: list[str] = []
        for cell in entry:
            s = "" if cell is None else str(cell)
            if len(s) > MAX_TABLE_CELL_LENGTH:
                raise HomeAssistantError(
                    f"cell length {len(s)} exceeds maximum {MAX_TABLE_CELL_LENGTH}"
                )
            pair.append(_strip_controls(s))
        out.append(pair)
    return out


def open_local_image_no_follow(path: Path, *, max_bytes: int | None = None) -> bytes:
    """Open ``path`` with ``O_NOFOLLOW`` and return its bytes.

    Used together with :func:`_validate_local_path_sync` to defeat
    TOCTOU symlink swaps between stat and open. Caller is expected to
    have already validated the path (size, extension, allowlist).
    """
    if max_bytes is None:
        max_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    return _read_no_follow(path, max_bytes=max_bytes, kind="Image")


def open_local_font_no_follow(path: Path, *, max_bytes: int | None = None) -> bytes:
    """Open ``path`` with ``O_NOFOLLOW`` and return its bytes (for fonts).

    Mirrors :func:`open_local_image_no_follow` but with the font size cap
    (``MAX_FONT_SIZE_BYTES``) instead of the image cap. The caller passes
    these bytes through :class:`io.BytesIO` to ``ImageFont.truetype`` so
    Pillow does not re-open the resolved path (which would otherwise be
    swappable for an attacker-controlled file between validate and load).
    """
    if max_bytes is None:
        max_bytes = MAX_FONT_SIZE_BYTES
    return _read_no_follow(path, max_bytes=max_bytes, kind="Font")


def _read_no_follow(path: Path, *, max_bytes: int, kind: str) -> bytes:
    """Common O_NOFOLLOW open + size check for image / font readers."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise HomeAssistantError(f"{kind} path is not a regular file")
        if st.st_size > max_bytes:
            mb = max_bytes // (1024 * 1024)
            raise HomeAssistantError(f"{kind} file too large (max {mb}MB)")
        with os.fdopen(fd, "rb", closefd=True) as handle:
            fd = -1  # ownership transferred to the file object
            return handle.read(max_bytes + 1)
    finally:
        if fd >= 0:
            os.close(fd)


def write_file_no_follow(path: str, data: bytes) -> None:
    """Write ``data`` to ``path`` with ``O_NOFOLLOW`` (S-M2).

    The path-validation step at the call site uses ``Path.resolve()``;
    a co-resident attacker who can plant a symlink between validation
    and write would otherwise make us overwrite the symlink target.
    ``O_NOFOLLOW`` makes the open fail with ``ELOOP`` if the leaf is a
    symlink. ``O_EXCL`` + ``O_CREAT`` would refuse to clobber an
    existing file, but preview writes intentionally overwrite — so we
    pair ``O_NOFOLLOW`` with ``O_TRUNC`` and explicit owner-only mode.

    Blocking; call from an executor thread.
    """
    fd = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        with os.fdopen(fd, "wb", closefd=True) as handle:
            fd = -1
            handle.write(data)
    finally:
        if fd >= 0:
            os.close(fd)


# ---------------------------------------------------------------------------
# Base64 data URI validation.
# ---------------------------------------------------------------------------


def validate_base64_image(value: str) -> bytes:
    """Decode a ``data:image/...;base64,...`` URI and enforce the size cap.

    Caps the input length **before** regex/decoding so an attacker
    cannot OOM us via a 200 MB base64 string.
    """
    if not isinstance(value, str):
        raise HomeAssistantError("Base64 image must be a string")
    if len(value) > MAX_BASE64_INPUT_BYTES:
        raise HomeAssistantError(
            f"Base64 image string too large (max ~{MAX_IMAGE_SIZE_MB}MB decoded)"
        )

    match = _DATA_URI_RE.match(value.strip())
    if not match:
        raise HomeAssistantError(
            "Base64 image must be a data:image/<subtype>;base64,... URI "
            "with subtype png/jpeg/jpg/gif/bmp/tiff/webp"
        )

    # Strip whitespace via bytes.translate instead of re.sub to avoid an
    # extra full-size string allocation.
    encoded_bytes = match.group("data").encode("ascii", errors="ignore")
    encoded_bytes = encoded_bytes.translate(None, b" \t\r\n")
    try:
        raw = base64.b64decode(encoded_bytes, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HomeAssistantError(f"Invalid base64 data: {exc}") from exc

    if len(raw) > MAX_IMAGE_SIZE_MB * 1024 * 1024:
        raise HomeAssistantError(f"Image too large (max {MAX_IMAGE_SIZE_MB}MB)")
    return raw


# ---------------------------------------------------------------------------
# Entity-id and choice validation.
# ---------------------------------------------------------------------------


_ENTITY_OBJECT_RE = re.compile(rf"^[a-z0-9_]{{1,{MAX_ENTITY_ID_OBJECT_LEN}}}$")


def validate_entity_id_for_domain(value: str, domain: str) -> str:
    """Validate ``value`` is an entity_id in the given domain."""
    if not isinstance(value, str):
        raise HomeAssistantError("Entity id must be a string")
    parts = value.split(".")
    if len(parts) != 2 or parts[0] != domain or not parts[1]:
        raise HomeAssistantError(f"Expected entity_id in domain '{domain}', got: {value}")
    if not _ENTITY_OBJECT_RE.match(parts[1]):
        raise HomeAssistantError(f"Invalid entity_id: {value}")
    return value


def _validate_choice(value: Any, choices: frozenset[Any], field_name: str) -> Any:
    """Return ``value`` if it is in ``choices``; otherwise raise.

    Uses :class:`ServiceValidationError` so the failure surfaces in the
    HA frontend as a translatable user-facing message rather than as an
    integration fault.
    """
    if value not in choices:
        raise ServiceValidationError(
            f"{field_name} must be one of {sorted(choices)}; got {value!r}"
        )
    return value


def validate_dither_mode(value: str) -> str:
    """Whitelist dither mode against ``DITHER_MODES``."""
    if not isinstance(value, str):
        raise ServiceValidationError("dither must be a string")
    return str(_validate_choice(value, DITHER_MODES, "dither"))


def validate_impl_mode(value: str) -> str:
    """Whitelist python-escpos image impl against ``IMPL_MODES``."""
    if not isinstance(value, str):
        raise ServiceValidationError("impl must be a string")
    return str(_validate_choice(value, IMPL_MODES, "impl"))


def validate_rotation(value: Any) -> int:
    """Validate rotation angle is one of 0/90/180/270."""
    try:
        rotation = int(value)
    except (TypeError, ValueError) as exc:
        raise ServiceValidationError("rotation must be an integer") from exc
    return int(_validate_choice(rotation, ROTATION_VALUES, "rotation"))


def validate_numeric_input(value: Any, min_val: int, max_val: int, field_name: str) -> int:
    """Validate numeric input within bounds."""
    try:
        num_value = int(value)
    except (TypeError, ValueError) as exc:
        raise HomeAssistantError(f"{field_name} must be a valid integer") from exc

    if not (min_val <= num_value <= max_val):
        raise HomeAssistantError(f"{field_name} must be between {min_val} and {max_val}")

    return num_value


# ---------------------------------------------------------------------------
# Log sanitization.
# ---------------------------------------------------------------------------

# Bluetooth MACs are hardware identifiers (treated as personal data under
# GDPR). Redact while preserving the OUI (first 3 octets) so support logs
# remain useful for vendor lookups without exposing the full address.
_MAC_RE = re.compile(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")

_DEFAULT_SENSITIVE_FIELDS = (
    "password",
    "token",
    "key",
    "secret",
    "data",
    "text",
    "address",
    "mac",
    "alias",
    # New: redact image-pipeline field labels (URLs, file paths, hostnames).
    "url",
    "path",
    "host",
    "image",
    "source",
)
_DEFAULT_FIELD_RE = re.compile(
    rf"({'|'.join(_DEFAULT_SENSITIVE_FIELDS)})=([^\s,)]+)",
    re.IGNORECASE,
)

# URL userinfo: `scheme://user:pass@host/...` → `scheme://[REDACTED]@host/...`.
_URL_USERINFO_RE = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)[^@/\s]+@")

# Redact bare HA-style filesystem paths so error text from PIL/aiohttp
# doesn't leak install layout. Order matters: list longer prefixes first.
_PATH_PREFIXES = (
    "/addon_configs/",
    "/config/",
    "/media/",
    "/share/",
    "/ssl/",
    "/data/",
)
_PATH_RE = re.compile(
    r"(?P<prefix>" + "|".join(re.escape(p) for p in _PATH_PREFIXES) + r")[^\s'\")]+"
)


def sanitize_log_message(message: str, sensitive_fields: list[str] | None = None) -> str:
    """Sanitize log messages to prevent information disclosure.

    Redacts named ``field=value`` pairs, URL userinfo, filesystem paths
    under HA's standard mount points, and Bluetooth MACs (preserving the
    OUI). Idempotent.
    """
    sanitized = message
    if "=" in sanitized:
        if sensitive_fields is None:
            sanitized = _DEFAULT_FIELD_RE.sub(r"\1=[REDACTED]", sanitized)
        else:
            for field in sensitive_fields:
                pattern = rf"({field})=([^\s,)]+)"
                sanitized = re.sub(pattern, r"\1=[REDACTED]", sanitized, flags=re.IGNORECASE)

    if "://" in sanitized:
        sanitized = _URL_USERINFO_RE.sub(r"\g<scheme>[REDACTED]@", sanitized)

    if "/" in sanitized:
        sanitized = _PATH_RE.sub(r"\g<prefix>[REDACTED]", sanitized)

    if ":" in sanitized or "-" in sanitized:
        sanitized = _MAC_RE.sub(lambda m: m.group(0)[:8] + ":XX:XX:XX", sanitized)

    return sanitized


# ---------------------------------------------------------------------------
# Misc validators (existing, unchanged behavior).
# ---------------------------------------------------------------------------


def validate_timeout(timeout: float) -> float:
    """Validate timeout value."""
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise HomeAssistantError("Timeout must be a positive number")

    if timeout > 300:
        raise HomeAssistantError("Timeout cannot exceed 300 seconds")

    return float(timeout)


_BT_MAC_RE = re.compile(r"^([0-9A-F]{2}:){5}[0-9A-F]{2}$")


def validate_bluetooth_mac(mac: str) -> str:
    """Validate and normalize a Bluetooth MAC address."""
    if not isinstance(mac, str):
        raise HomeAssistantError("Bluetooth MAC must be a string")
    candidate = mac.strip().upper().replace("-", ":")
    if not _BT_MAC_RE.match(candidate):
        raise HomeAssistantError("Invalid Bluetooth MAC address; expected format AA:BB:CC:DD:EE:FF")
    return candidate


def validate_rfcomm_channel(channel: int) -> int:
    """Validate an RFCOMM channel number (1-30)."""
    try:
        value = int(channel)
    except (ValueError, TypeError) as exc:
        raise HomeAssistantError("RFCOMM channel must be an integer") from exc
    if not 1 <= value <= 30:
        raise HomeAssistantError("RFCOMM channel must be between 1 and 30")
    return value


    # B-L1: ``secure_service_call`` was a never-implemented pass-through
    # decorator from an earlier iteration. The cross-cutting validation
    # it advertised (exception sanitisation in particular) now lives in
    # ``services._handler_utils._wrap_unexpected`` and ``_for_each_target``.
    # No callers remained, so the decorator was removed.
