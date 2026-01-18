"""
Security tests for HA ESCPOS Thermal Printer integration.

This module contains tests to verify security features and validate
that security vulnerabilities are properly mitigated.
"""

from unittest.mock import patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.escpos_printer.security import (
    MAX_BARCODE_LENGTH,
    MAX_BEEP_TIMES,
    MAX_FEED_LINES,
    MAX_QR_DATA_LENGTH,
    MAX_TEXT_LENGTH,
    sanitize_log_message,
    validate_barcode_data,
    validate_image_url,
    validate_local_image_path,
    validate_numeric_input,
    validate_qr_data,
    validate_text_input,
    validate_timeout,
)


class TestInputValidation:
    """Test input validation functions."""

    def test_validate_text_input_valid(self):  # type: ignore[no-untyped-def]
        """Test valid text input validation."""
        text = "Hello, World!"
        result = validate_text_input(text)
        assert result == text

    def test_validate_text_input_max_length(self):  # type: ignore[no-untyped-def]
        """Test text input length validation."""
        long_text = "x" * (MAX_TEXT_LENGTH + 1)
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_text_input(long_text)

    def test_validate_text_input_control_chars(self):  # type: ignore[no-untyped-def]
        """Test removal of control characters."""
        text_with_control = "Hello\x00World\x01Test"
        result = validate_text_input(text_with_control)
        assert "\x00" not in result
        assert "\x01" not in result
        assert result == "HelloWorldTest"

    def test_validate_text_input_empty(self):  # type: ignore[no-untyped-def]
        """Test empty text input."""
        result = validate_text_input("")
        assert result == ""

    def test_validate_text_input_none(self):  # type: ignore[no-untyped-def]
        """Test None text input."""
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_text_input(None)


class TestQRDataValidation:
    """Test QR code data validation."""

    def test_validate_qr_data_valid(self):  # type: ignore[no-untyped-def]
        """Test valid QR data."""
        data = "https://example.com"
        result = validate_qr_data(data)
        assert result == data

    def test_validate_qr_data_max_length(self):  # type: ignore[no-untyped-def]
        """Test QR data length validation."""
        long_data = "x" * (MAX_QR_DATA_LENGTH + 1)
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_qr_data(long_data)

    def test_validate_qr_data_empty(self):  # type: ignore[no-untyped-def]
        """Test empty QR data."""
        with pytest.raises(HomeAssistantError, match="cannot be empty"):
            validate_qr_data("")

    def test_validate_qr_data_whitespace_only(self):  # type: ignore[no-untyped-def]
        """Test whitespace-only QR data."""
        with pytest.raises(HomeAssistantError, match="cannot be empty"):
            validate_qr_data("   ")


class TestBarcodeDataValidation:
    """Test barcode data validation."""

    def test_validate_barcode_data_valid(self):  # type: ignore[no-untyped-def]
        """Test valid barcode data."""
        code = "123456789"
        bc_type = "CODE128"
        result_code, result_type = validate_barcode_data(code, bc_type)
        assert result_code == code
        assert result_type == bc_type.upper()

    def test_validate_barcode_data_max_length(self):  # type: ignore[no-untyped-def]
        """Test barcode data length validation."""
        long_code = "x" * (MAX_BARCODE_LENGTH + 1)
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_barcode_data(long_code, "CODE128")

    def test_validate_barcode_data_empty(self):  # type: ignore[no-untyped-def]
        """Test empty barcode data."""
        with pytest.raises(HomeAssistantError, match="cannot be empty"):
            validate_barcode_data("", "CODE128")

    def test_validate_barcode_data_case_insensitive(self):  # type: ignore[no-untyped-def]
        """Test barcode type case insensitivity."""
        _code, bc_type = validate_barcode_data("123", "code39")
        assert bc_type == "CODE39"


class TestImageURLValidation:
    """Test image URL validation."""

    def test_validate_image_url_https(self):  # type: ignore[no-untyped-def]
        """Test valid HTTPS URL."""
        url = "https://example.com/image.png"
        result = validate_image_url(url)
        assert result == url

    def test_validate_image_url_http(self):  # type: ignore[no-untyped-def]
        """Test valid HTTP URL."""
        url = "http://example.com/image.jpg"
        result = validate_image_url(url)
        assert result == url

    def test_validate_image_url_invalid_scheme(self):  # type: ignore[no-untyped-def]
        """Test invalid URL scheme."""
        with pytest.raises(HomeAssistantError, match="Invalid URL scheme"):
            validate_image_url("ftp://example.com/image.png")

    def test_validate_image_url_no_hostname(self):  # type: ignore[no-untyped-def]
        """Test URL without hostname."""
        with pytest.raises(HomeAssistantError, match="must include a valid hostname"):
            validate_image_url("https:///image.png")

    def test_validate_image_url_too_long(self):  # type: ignore[no-untyped-def]
        """Test overly long URL."""
        long_url = "https://example.com/" + "x" * 2000
        with pytest.raises(HomeAssistantError, match="URL is too long"):
            validate_image_url(long_url)


class TestLocalImagePathValidation:
    """Test local image path validation."""

    def test_validate_local_image_path_valid(self):  # type: ignore[no-untyped-def]
        """Test valid local image path."""
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024):
            result = validate_local_image_path("/path/to/image.png")
            assert result == "/path/to/image.png"

    def test_validate_local_image_path_traversal(self):  # type: ignore[no-untyped-def]
        """Test path traversal protection."""
        with pytest.raises(HomeAssistantError, match="forbidden characters"):
            validate_local_image_path("../../../etc/passwd")

    def test_validate_local_image_path_invalid_extension(self):  # type: ignore[no-untyped-def]
        """Test invalid file extension."""
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=1024):
            with pytest.raises(HomeAssistantError, match="not allowed"):
                validate_local_image_path("/path/to/script.py")

    def test_validate_local_image_path_file_not_exists(self):  # type: ignore[no-untyped-def]
        """Test non-existent file."""
        with patch("os.path.isfile", return_value=False):
            with pytest.raises(HomeAssistantError, match="does not exist"):
                validate_local_image_path("/nonexistent/image.png")

    def test_validate_local_image_path_too_large(self):  # type: ignore[no-untyped-def]
        """Test file size limit."""
        with patch("os.path.isfile", return_value=True), \
             patch("os.path.getsize", return_value=20 * 1024 * 1024):  # 20MB
            with pytest.raises(HomeAssistantError, match="too large"):
                validate_local_image_path("/path/to/large_image.png")


class TestNumericInputValidation:
    """Test numeric input validation."""

    def test_validate_numeric_input_valid(self):  # type: ignore[no-untyped-def]
        """Test valid numeric input."""
        result = validate_numeric_input(5, 0, 10, "test_value")
        assert result == 5

    def test_validate_numeric_input_string(self):  # type: ignore[no-untyped-def]
        """Test string numeric input."""
        result = validate_numeric_input("7", 0, 10, "test_value")
        assert result == 7

    def test_validate_numeric_input_below_min(self):  # type: ignore[no-untyped-def]
        """Test value below minimum."""
        with pytest.raises(HomeAssistantError, match="must be between"):
            validate_numeric_input(-1, 0, 10, "test_value")

    def test_validate_numeric_input_above_max(self):  # type: ignore[no-untyped-def]
        """Test value above maximum."""
        with pytest.raises(HomeAssistantError, match="must be between"):
            validate_numeric_input(15, 0, 10, "test_value")

    def test_validate_numeric_input_invalid_type(self):  # type: ignore[no-untyped-def]
        """Test invalid input type."""
        with pytest.raises(HomeAssistantError, match="must be a valid integer"):
            validate_numeric_input("not_a_number", 0, 10, "test_value")


class TestLogSanitization:
    """Test log message sanitization."""

    def test_sanitize_log_message_no_sensitive(self):  # type: ignore[no-untyped-def]
        """Test sanitization with no sensitive data."""
        message = "Processing user request"
        result = sanitize_log_message(message)
        assert result == message

    def test_sanitize_log_message_with_sensitive(self):  # type: ignore[no-untyped-def]
        """Test sanitization with sensitive data."""
        message = "Login attempt for user=test password=secret123 token=abc123"
        result = sanitize_log_message(message, ["password", "token"])
        assert "[REDACTED]" in result
        assert "secret123" not in result
        assert "abc123" not in result

    def test_sanitize_log_message_case_insensitive(self):  # type: ignore[no-untyped-def]
        """Test case-insensitive sanitization."""
        message = "PASSWORD=secret TOKEN=abc"
        result = sanitize_log_message(message, ["password", "token"])
        assert "[REDACTED]" in result
        assert "secret" not in result


class TestTimeoutValidation:
    """Test timeout validation."""

    def test_validate_timeout_valid(self):  # type: ignore[no-untyped-def]
        """Test valid timeout."""
        result = validate_timeout(5.0)
        assert result == 5.0

    def test_validate_timeout_zero(self):  # type: ignore[no-untyped-def]
        """Test zero timeout."""
        with pytest.raises(HomeAssistantError, match="must be a positive number"):
            validate_timeout(0)

    def test_validate_timeout_negative(self):  # type: ignore[no-untyped-def]
        """Test negative timeout."""
        with pytest.raises(HomeAssistantError, match="must be a positive number"):
            validate_timeout(-1)

    def test_validate_timeout_too_large(self):  # type: ignore[no-untyped-def]
        """Test timeout too large."""
        with pytest.raises(HomeAssistantError, match="cannot exceed"):
            validate_timeout(400)


class TestSecurityConstants:
    """Test security constant values."""

    def test_max_text_length(self):  # type: ignore[no-untyped-def]
        """Test MAX_TEXT_LENGTH constant."""
        assert MAX_TEXT_LENGTH == 10000

    def test_max_qr_data_length(self):  # type: ignore[no-untyped-def]
        """Test MAX_QR_DATA_LENGTH constant."""
        assert MAX_QR_DATA_LENGTH == 2000

    def test_max_barcode_length(self):  # type: ignore[no-untyped-def]
        """Test MAX_BARCODE_LENGTH constant."""
        assert MAX_BARCODE_LENGTH == 100

    def test_max_feed_lines(self):  # type: ignore[no-untyped-def]
        """Test MAX_FEED_LINES constant."""
        assert MAX_FEED_LINES == 50

    def test_max_beep_times(self):  # type: ignore[no-untyped-def]
        """Test MAX_BEEP_TIMES constant."""
        assert MAX_BEEP_TIMES == 10


class TestIntegrationSecurity:
    """Integration tests for security features."""

    def test_comprehensive_input_validation(self):  # type: ignore[no-untyped-def]
        """Test comprehensive input validation workflow."""
        # This would test the full validation pipeline
        # for a typical service call

        # Test text validation
        text = validate_text_input("Valid text")

        # Test numeric validation
        feed = validate_numeric_input(5, 0, MAX_FEED_LINES, "feed")

        # Test URL validation
        url = validate_image_url("https://example.com/image.png")

        # All validations should pass
        assert text == "Valid text"
        assert feed == 5
        assert url == "https://example.com/image.png"

    @pytest.mark.parametrize(("invalid_input", "expected_error"), [
        ("x" * 10001, "exceeds maximum"),
        ("", "cannot be empty"),
        ("   ", "cannot be empty"),
        (None, "must be a string"),
    ])
    def test_qr_validation_edge_cases(self, invalid_input, expected_error):  # type: ignore[no-untyped-def]
        """Test QR validation edge cases."""
        with pytest.raises(HomeAssistantError, match=expected_error):
            validate_qr_data(invalid_input)
