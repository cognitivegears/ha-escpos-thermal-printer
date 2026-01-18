"""
Security utilities for ESCPOS Thermal Printer integration.

This module provides security-focused validation and sanitization functions
to protect against common vulnerabilities including injection attacks,
resource exhaustion, and information disclosure.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any
from urllib.parse import urlparse

from homeassistant.exceptions import HomeAssistantError

_LOGGER = logging.getLogger(__name__)

# Security constants
MAX_TEXT_LENGTH = 10000  # Maximum text length to prevent resource exhaustion
MAX_QR_DATA_LENGTH = 2000  # Maximum QR code data length
MAX_BARCODE_LENGTH = 100  # Maximum barcode data length
MAX_IMAGE_SIZE_MB = 10  # Maximum image download size in MB
MAX_FEED_LINES = 50  # Maximum feed lines to prevent paper waste
MAX_BEEP_TIMES = 10  # Maximum beep repetitions

# URL validation patterns
VALID_URL_SCHEMES = {"http", "https"}
VALID_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}

# Path traversal protection
# Do not block path separators; instead, prevent traversal sequences and unsafe expansions.
FORBIDDEN_PATH_SEQUENCES = {"..", "~", "$", "`"}


def validate_text_input(text: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Validate and sanitize text input.

    Args:
        text: Input text to validate
        max_length: Maximum allowed length

    Returns:
        Sanitized text

    Raises:
        HomeAssistantError: If validation fails
    """
    if not isinstance(text, str):
        raise HomeAssistantError("Text input must be a string")

    if len(text) > max_length:
        raise HomeAssistantError(f"Text length exceeds maximum of {max_length} characters")

    # Remove null bytes and other control characters that could cause issues
    sanitized = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)

    # Log warning for potentially suspicious content without exposing the content
    if len(sanitized) != len(text):
        _LOGGER.warning("Text input contained control characters that were removed")

    return sanitized


def validate_qr_data(data: str) -> str:
    """Validate QR code data.

    Args:
        data: QR code data to validate

    Returns:
        Validated data

    Raises:
        HomeAssistantError: If validation fails
    """
    if not isinstance(data, str):
        raise HomeAssistantError("QR data must be a string")

    if len(data) > MAX_QR_DATA_LENGTH:
        raise HomeAssistantError(f"QR data length exceeds maximum of {MAX_QR_DATA_LENGTH} characters")

    if not data.strip():
        raise HomeAssistantError("QR data cannot be empty")

    return data


def validate_barcode_data(code: str, bc_type: str) -> tuple[str, str]:
    """Validate barcode data and type.

    Args:
        code: Barcode data
        bc_type: Barcode type

    Returns:
        Tuple of (validated_code, validated_bc_type)

    Raises:
        HomeAssistantError: If validation fails
    """
    if not isinstance(code, str) or not isinstance(bc_type, str):
        raise HomeAssistantError("Barcode code and type must be strings")

    if len(code) > MAX_BARCODE_LENGTH:
        raise HomeAssistantError(f"Barcode data length exceeds maximum of {MAX_BARCODE_LENGTH} characters")

    if not code.strip():
        raise HomeAssistantError("Barcode data cannot be empty")

    # Validate barcode type (expanded set with common aliases)
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
    # Normalize aliases to common forms expected by python-escpos
    bc_canonical = aliases.get(bc_upper, bc_upper)
    return code, bc_canonical


def validate_image_url(url: str) -> str:
    """Validate image URL for security.

    Args:
        url: Image URL to validate

    Returns:
        Validated URL

    Raises:
        HomeAssistantError: If validation fails
    """
    if not isinstance(url, str):
        raise HomeAssistantError("Image URL must be a string")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise HomeAssistantError(f"Invalid URL format: {e}") from e

    # Validate scheme
    if parsed.scheme not in VALID_URL_SCHEMES:
        raise HomeAssistantError(f"Invalid URL scheme. Only {VALID_URL_SCHEMES} are allowed")

    # Validate hostname exists
    if not parsed.hostname:
        raise HomeAssistantError("URL must include a valid hostname")

    # Basic length check (tightened to align with tests/policies)
    if len(url) > 2000:
        raise HomeAssistantError("URL is too long")

    return url


def validate_local_image_path(path: str, allowed_extensions: set[str] = VALID_IMAGE_EXTENSIONS) -> str:
    """Validate local image file path for security.

    Args:
        path: File path to validate
        allowed_extensions: Set of allowed file extensions

    Returns:
        Validated and normalized path

    Raises:
        HomeAssistantError: If validation fails
    """
    if not isinstance(path, str):
        raise HomeAssistantError("Image path must be a string")

    # Basic check for traversal or shell-expansion risk
    if any(seq in path for seq in FORBIDDEN_PATH_SEQUENCES):
        # Keep message consistent with existing tests and docs
        raise HomeAssistantError("Path contains forbidden characters")

    # Normalize path to prevent directory traversal
    normalized_path = os.path.normpath(path)

    # Absolute paths are allowed; Home Assistant typically uses /config paths.
    # Additional runtime restrictions (e.g., whitelisting /config or media) should
    # be enforced by the caller/environment if needed.

    # Validate file extension
    _, ext = os.path.splitext(normalized_path.lower())
    if ext not in allowed_extensions:
        raise HomeAssistantError(f"File extension '{ext}' not allowed. Allowed: {allowed_extensions}")

    # Check if file exists and is readable
    if not os.path.isfile(normalized_path):
        raise HomeAssistantError("Image file does not exist or is not a regular file")

    # Basic file size check (prevent extremely large files)
    try:
        file_size = os.path.getsize(normalized_path)
        if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
            raise HomeAssistantError(f"Image file too large (max {MAX_IMAGE_SIZE_MB}MB)")
    except OSError as e:
        raise HomeAssistantError(f"Cannot access image file: {e}") from e

    return normalized_path


def validate_numeric_input(value: Any, min_val: int, max_val: int, field_name: str) -> int:
    """Validate numeric input within bounds.

    Args:
        value: Value to validate
        min_val: Minimum allowed value
        max_val: Maximum allowed value
        field_name: Name of the field for error messages

    Returns:
        Validated integer value

    Raises:
        HomeAssistantError: If validation fails
    """
    try:
        num_value = int(value)
    except (ValueError, TypeError) as e:
        raise HomeAssistantError(f"{field_name} must be a valid integer") from e

    if not (min_val <= num_value <= max_val):
        raise HomeAssistantError(f"{field_name} must be between {min_val} and {max_val}")

    return num_value


def sanitize_log_message(message: str, sensitive_fields: list[str] | None = None) -> str:
    """Sanitize log messages to prevent information disclosure.

    Args:
        message: Log message to sanitize
        sensitive_fields: List of field names that should be redacted

    Returns:
        Sanitized log message
    """
    if sensitive_fields is None:
        sensitive_fields = ["password", "token", "key", "secret", "data", "text"]

    sanitized = message

    # Redact sensitive field values in log-like formats
    for field in sensitive_fields:
        # Pattern to match field=value in logs
        pattern = rf'({field})=([^\s,)]+)'
        sanitized = re.sub(pattern, r'\1=[REDACTED]', sanitized, flags=re.IGNORECASE)

    return sanitized


def validate_timeout(timeout: float) -> float:
    """Validate timeout value.

    Args:
        timeout: Timeout value in seconds

    Returns:
        Validated timeout

    Raises:
        HomeAssistantError: If validation fails
    """
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise HomeAssistantError("Timeout must be a positive number")

    if timeout > 300:  # 5 minutes max
        raise HomeAssistantError("Timeout cannot exceed 300 seconds")

    return float(timeout)


# Security-focused validation decorators
def secure_service_call(func):  # type: ignore[no-untyped-def]
    """Decorator to add security validation to service calls."""
    async def wrapper(*args, **kwargs):  # type: ignore[no-untyped-def]
        # Add any cross-cutting security validations here
        return await func(*args, **kwargs)
    return wrapper
