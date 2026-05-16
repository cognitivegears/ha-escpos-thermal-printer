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
MAX_URL_LENGTH = 2000

# Local file validation. HEIC/HEIF/AVIF are accepted when ``pillow-heif``
# is installed (see ``printer/image_processor._register_heif_opener``).
# The allowlist is the union of every format we *might* be able to
# decode — Pillow's ``formats=`` parameter in the actual decode step is
# the real gate, so listing them here without the opener is a no-op.
VALID_IMAGE_EXTENSIONS = frozenset(
    {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp",
     ".heic", ".heif", ".avif"}
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
        raise HomeAssistantError(
            f"Text length exceeds maximum of {max_length} characters"
        )

    # Strip C0 control characters except CR/LF/HT (which ESC/POS handles).
    sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

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
        "EAN13", "EAN8", "UPCA", "UPC-A", "UPC-E",
        "CODE39", "CODE93", "CODE128",
        "ITF", "ITF14", "CODABAR", "NW7",
        "JAN", "JAN13", "JAN8",
    }
    bc_upper = bc_type.upper()
    if bc_upper not in valid_types:
        _LOGGER.warning(
            "Unknown barcode type '%s', proceeding with caution", bc_type
        )
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
    # legitimate one in logs/toasts. Reject `xn--`-encoded hostnames.
    if "xn--" in parsed.hostname.lower():
        raise HomeAssistantError(
            "Internationalized (IDN/punycode) hostnames are not allowed"
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
        raise HomeAssistantError(
            f"Could not resolve image URL hostname: {exc}"
        ) from exc
    addrs = sorted({str(info[4][0]) for info in infos})
    if not addrs:
        raise HomeAssistantError("Could not resolve image URL hostname")
    return addrs


async def validate_image_url_and_resolve(
    hass: HomeAssistant, url: str
) -> tuple[str, list[str]]:
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
    addrs = await hass.async_add_executor_job(
        _resolve_hostname_sync, hostname, parsed.port
    )
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
        raise HomeAssistantError(
            "Image file does not exist or is not a regular file"
        ) from exc
    except OSError as exc:
        raise HomeAssistantError(f"Cannot access image file: {exc}") from exc

    if resolved.suffix.lower() not in allowed:
        raise HomeAssistantError(
            f"File extension '{resolved.suffix}' not allowed. "
            f"Allowed: {sorted(allowed)}"
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


def open_local_image_no_follow(
    path: Path, *, max_bytes: int | None = None
) -> bytes:
    """Open ``path`` with ``O_NOFOLLOW`` and return its bytes.

    Used together with :func:`_validate_local_path_sync` to defeat
    TOCTOU symlink swaps between stat and open. Caller is expected to
    have already validated the path (size, extension, allowlist).
    """
    if max_bytes is None:
        max_bytes = MAX_IMAGE_SIZE_MB * 1024 * 1024
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise HomeAssistantError("Image path is not a regular file")
        if st.st_size > max_bytes:
            mb = max_bytes // (1024 * 1024)
            raise HomeAssistantError(f"Image file too large (max {mb}MB)")
        with os.fdopen(fd, "rb", closefd=True) as handle:
            fd = -1  # ownership transferred to the file object
            return handle.read(max_bytes + 1)
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
        raise HomeAssistantError(
            f"Expected entity_id in domain '{domain}', got: {value}"
        )
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


def validate_numeric_input(
    value: Any, min_val: int, max_val: int, field_name: str
) -> int:
    """Validate numeric input within bounds."""
    try:
        num_value = int(value)
    except (TypeError, ValueError) as exc:
        raise HomeAssistantError(
            f"{field_name} must be a valid integer"
        ) from exc

    if not (min_val <= num_value <= max_val):
        raise HomeAssistantError(
            f"{field_name} must be between {min_val} and {max_val}"
        )

    return num_value


# ---------------------------------------------------------------------------
# Log sanitization.
# ---------------------------------------------------------------------------

# Bluetooth MACs are hardware identifiers (treated as personal data under
# GDPR). Redact while preserving the OUI (first 3 octets) so support logs
# remain useful for vendor lookups without exposing the full address.
_MAC_RE = re.compile(r"\b([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")

_DEFAULT_SENSITIVE_FIELDS = (
    "password", "token", "key", "secret", "data", "text",
    "address", "mac", "alias",
    # New: redact image-pipeline field labels (URLs, file paths, hostnames).
    "url", "path", "host", "image", "source",
)
_DEFAULT_FIELD_RE = re.compile(
    rf'({"|".join(_DEFAULT_SENSITIVE_FIELDS)})=([^\s,)]+)',
    re.IGNORECASE,
)

# URL userinfo: `scheme://user:pass@host/...` → `scheme://[REDACTED]@host/...`.
_URL_USERINFO_RE = re.compile(r"(?P<scheme>[A-Za-z][A-Za-z0-9+.\-]*://)[^@/\s]+@")

# Redact bare HA-style filesystem paths so error text from PIL/aiohttp
# doesn't leak install layout. Order matters: list longer prefixes first.
_PATH_PREFIXES = (
    "/addon_configs/", "/config/", "/media/", "/share/", "/ssl/", "/data/",
)
_PATH_RE = re.compile(
    r"(?P<prefix>" + "|".join(re.escape(p) for p in _PATH_PREFIXES) + r")[^\s'\")]+"
)


def sanitize_log_message(
    message: str, sensitive_fields: list[str] | None = None
) -> str:
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
                sanitized = re.sub(
                    pattern, r"\1=[REDACTED]", sanitized, flags=re.IGNORECASE
                )

    if "://" in sanitized:
        sanitized = _URL_USERINFO_RE.sub(r"\g<scheme>[REDACTED]@", sanitized)

    if "/" in sanitized:
        sanitized = _PATH_RE.sub(r"\g<prefix>[REDACTED]", sanitized)

    if ":" in sanitized or "-" in sanitized:
        sanitized = _MAC_RE.sub(
            lambda m: m.group(0)[:8] + ":XX:XX:XX", sanitized
        )

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
        raise HomeAssistantError(
            "Invalid Bluetooth MAC address; expected format AA:BB:CC:DD:EE:FF"
        )
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


def secure_service_call(func):  # type: ignore[no-untyped-def]
    """Decorator hook for cross-cutting security validations."""

    async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        return await func(*args, **kwargs)

    return wrapper
