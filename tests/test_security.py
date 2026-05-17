"""Security tests for the ESC/POS Thermal Printer integration.

Covers:

- The legacy validators (text/QR/barcode/numeric/timeout) — happy paths.
- The new validators added on `feature/image_updates` (`validate_base64_image`,
  `validate_entity_id_for_domain`, choice validators) — Phase 3 T-H3.
- URL validation hardening (credentials, IDN, ports, length) — Phase 3 T-C1.
- `sanitize_log_message` URL userinfo + path redaction — Phase 3 T-H2.
- Local-path validation: `pathlib.Path.resolve(strict=True)` semantics,
  symlink behaviour, allowlist enforcement — Phase 3 T-C2.
"""

from __future__ import annotations

import base64

from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import pytest

from custom_components.escpos_printer.security import (
    MAX_BARCODE_LENGTH,
    MAX_BEEP_TIMES,
    MAX_FEED_LINES,
    MAX_IMAGE_SIZE_MB,
    MAX_QR_DATA_LENGTH,
    MAX_TEXT_LENGTH,
    VALID_IMAGE_EXTENSIONS,
    _validate_local_path_sync,
    sanitize_log_message,
    validate_barcode_data,
    validate_base64_image,
    validate_dither_mode,
    validate_entity_id_for_domain,
    validate_image_url,
    validate_impl_mode,
    validate_numeric_input,
    validate_qr_data,
    validate_rotation,
    validate_text_input,
    validate_timeout,
)

# ---------------------------------------------------------------------------
# Text / QR / barcode (legacy).
# ---------------------------------------------------------------------------


class TestInputValidation:
    def test_validate_text_input_valid(self):  # type: ignore[no-untyped-def]
        assert validate_text_input("Hello, World!") == "Hello, World!"

    def test_validate_text_input_max_length(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_text_input("x" * (MAX_TEXT_LENGTH + 1))

    def test_validate_text_input_control_chars(self):  # type: ignore[no-untyped-def]
        result = validate_text_input("Hello\x00World\x01Test")
        assert "\x00" not in result
        assert "\x01" not in result
        assert result == "HelloWorldTest"

    def test_validate_text_input_none(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_text_input(None)


class TestQRDataValidation:
    def test_validate_qr_data_valid(self):  # type: ignore[no-untyped-def]
        assert validate_qr_data("https://example.com") == "https://example.com"

    def test_validate_qr_data_max_length(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_qr_data("x" * (MAX_QR_DATA_LENGTH + 1))

    def test_validate_qr_data_empty(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="cannot be empty"):
            validate_qr_data("")


class TestBarcodeDataValidation:
    def test_validate_barcode_data_valid(self):  # type: ignore[no-untyped-def]
        result_code, result_type = validate_barcode_data("123456789", "CODE128")
        assert result_code == "123456789"
        assert result_type == "CODE128"

    def test_validate_barcode_data_max_length(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_barcode_data("x" * (MAX_BARCODE_LENGTH + 1), "CODE128")


# ---------------------------------------------------------------------------
# URL validation (legacy + Phase 3 T-C1 hardening).
# ---------------------------------------------------------------------------


class TestImageURLValidation:
    def test_validate_image_url_https(self):  # type: ignore[no-untyped-def]
        url = "https://example.com/image.png"
        assert validate_image_url(url) == url

    def test_validate_image_url_invalid_scheme(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="Invalid URL scheme"):
            validate_image_url("ftp://example.com/image.png")

    def test_validate_image_url_no_hostname(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="hostname"):
            validate_image_url("https:///image.png")

    def test_validate_image_url_too_long(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="too long"):
            validate_image_url("https://example.com/" + "x" * 2000)

    @pytest.mark.parametrize(
        "url",
        [
            "https://user:pass@example.com/x.png",
            "http://admin:hunter2@example.com/x.png",
        ],
    )
    def test_validate_image_url_rejects_credentials(self, url):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="credentials"):
            validate_image_url(url)

    def test_validate_image_url_rejects_idn(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="IDN"):
            validate_image_url("https://xn--paypa-yfa.com/x.png")

    @pytest.mark.parametrize(
        "url",
        [
            "https://example.com:22/x.png",
            "https://example.com:8123/x.png",
            "http://example.com:25/x.png",
        ],
    )
    def test_validate_image_url_rejects_non_default_ports(self, url):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="port"):
            validate_image_url(url)


# ---------------------------------------------------------------------------
# Local-image path validation (T-C2: pathlib.resolve, symlinks).
# ---------------------------------------------------------------------------


class TestLocalImagePathValidation:
    def test_valid_local_image_path(self, tmp_path):  # type: ignore[no-untyped-def]
        path = tmp_path / "logo.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")
        resolved = _validate_local_path_sync(str(path))
        assert resolved == path.resolve()

    def test_local_image_path_missing(self, tmp_path):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="does not exist"):
            _validate_local_path_sync(str(tmp_path / "missing.png"))

    def test_local_image_path_invalid_extension(self, tmp_path):  # type: ignore[no-untyped-def]
        path = tmp_path / "script.py"
        path.write_text("nope")
        with pytest.raises(HomeAssistantError, match="not allowed"):
            _validate_local_path_sync(str(path))

    def test_local_image_path_too_large(self, tmp_path):  # type: ignore[no-untyped-def]
        path = tmp_path / "huge.png"
        path.write_bytes(b"\x00" * (MAX_IMAGE_SIZE_MB * 1024 * 1024 + 1))
        with pytest.raises(HomeAssistantError, match="too large"):
            _validate_local_path_sync(str(path))

    def test_local_image_path_resolves_symlinks(self, tmp_path):  # type: ignore[no-untyped-def]
        target = tmp_path / "real.png"
        target.write_bytes(b"\x89PNG\r\n\x1a\n")
        link = tmp_path / "alias.png"
        link.symlink_to(target)
        resolved = _validate_local_path_sync(str(link))
        # `Path.resolve(strict=True)` follows the symlink so the allowlist
        # check upstream sees the real target.
        assert resolved == target.resolve()

    def test_local_image_path_rejects_broken_symlink(self, tmp_path):  # type: ignore[no-untyped-def]
        link = tmp_path / "dead.png"
        link.symlink_to(tmp_path / "nonexistent.png")
        with pytest.raises(HomeAssistantError, match="does not exist"):
            _validate_local_path_sync(str(link))


# ---------------------------------------------------------------------------
# Numeric input validation.
# ---------------------------------------------------------------------------


class TestNumericInputValidation:
    def test_validate_numeric_input_valid(self):  # type: ignore[no-untyped-def]
        assert validate_numeric_input(5, 0, 10, "test_value") == 5

    def test_validate_numeric_input_below_min(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be between"):
            validate_numeric_input(-1, 0, 10, "x")

    def test_validate_numeric_input_invalid_type(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a valid integer"):
            validate_numeric_input("not_a_number", 0, 10, "x")


# ---------------------------------------------------------------------------
# T-H3: New choice / entity-id / base64 validators.
# ---------------------------------------------------------------------------


class TestEntityIdDomainValidation:
    def test_accepts_valid(self):  # type: ignore[no-untyped-def]
        assert validate_entity_id_for_domain("camera.front", "camera") == "camera.front"

    @pytest.mark.parametrize(
        "value",
        [
            "switch.front",          # wrong domain
            "camera.",               # missing object id
            "camera",                # missing dot
            "camera.Front-Door",     # uppercase + dash
            "camera." + "a" * 65,    # exceeds length cap (S-M6)
        ],
    )
    def test_rejects_invalid(self, value):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError):
            validate_entity_id_for_domain(value, "camera")


class TestRotationValidation:
    @pytest.mark.parametrize("v", [0, 90, 180, 270, "90"])
    def test_accepts(self, v):  # type: ignore[no-untyped-def]
        assert validate_rotation(v) in (0, 90, 180, 270)

    @pytest.mark.parametrize("v", [45, 360, -90, "north", None])
    def test_rejects(self, v):  # type: ignore[no-untyped-def]
        with pytest.raises(ServiceValidationError):
            validate_rotation(v)


class TestDitherImplValidation:
    @pytest.mark.parametrize("v", ["floyd-steinberg", "none", "threshold"])
    def test_dither_accepts(self, v):  # type: ignore[no-untyped-def]
        assert validate_dither_mode(v) == v

    def test_dither_rejects(self):  # type: ignore[no-untyped-def]
        with pytest.raises(ServiceValidationError):
            validate_dither_mode("ordered")

    @pytest.mark.parametrize("v", ["bitImageRaster", "graphics", "bitImageColumn"])
    def test_impl_accepts(self, v):  # type: ignore[no-untyped-def]
        assert validate_impl_mode(v) == v

    def test_impl_rejects(self):  # type: ignore[no-untyped-def]
        with pytest.raises(ServiceValidationError):
            validate_impl_mode("graphix")


class TestBase64ImageValidation:
    def test_accepts_valid_data_uri(self):  # type: ignore[no-untyped-def]
        raw = b"hello"
        uri = "data:image/png;base64," + base64.b64encode(raw).decode()
        assert validate_base64_image(uri) == raw

    @pytest.mark.parametrize(
        ("uri", "match"),
        [
            ("hello", "data:image"),
            ("data:text/plain;base64,aGk=", "data:image"),
            # S-L2 regression: svg+xml subtype must be rejected.
            ("data:image/svg+xml;base64,aGk=", "data:image"),
            # `!!!` doesn't match the base64 alphabet — the regex rejects
            # it before decode (giving the data-URI shape error).
            ("data:image/png;base64,!!!", "data:image"),
        ],
    )
    def test_rejects_invalid(self, uri, match):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match=match):
            validate_base64_image(uri)

    def test_rejects_oversized_input_pre_decode(self):  # type: ignore[no-untyped-def]
        # T-H1: a 200 MB base64 string must be rejected before decoding.
        # We don't measure tracemalloc here (CPython realloc costs); we
        # rely on the cap to short-circuit ahead of base64.b64decode.
        huge = "data:image/png;base64," + "A" * (200 * 1024 * 1024)
        with pytest.raises(HomeAssistantError, match="too large"):
            validate_base64_image(huge)


# ---------------------------------------------------------------------------
# T-H2: sanitize_log_message extensions (URL userinfo, file paths).
# ---------------------------------------------------------------------------


class TestLogSanitization:
    def test_no_sensitive(self):  # type: ignore[no-untyped-def]
        assert sanitize_log_message("Processing request") == "Processing request"

    def test_redacts_url_userinfo(self):  # type: ignore[no-untyped-def]
        msg = "Failed download: https://alice:hunter2@example.com/x.png timeout"
        result = sanitize_log_message(msg)
        assert "alice" not in result
        assert "hunter2" not in result
        assert "[REDACTED]@example.com" in result

    @pytest.mark.parametrize(
        "path",
        [
            "/config/www/secret.png",
            "/media/private/x.jpg",
            "/share/backup.png",
            "/ssl/cert.png",
            "/addon_configs/myaddon/cfg.png",
            "/data/state.png",
        ],
    )
    def test_redacts_filesystem_paths(self, path):  # type: ignore[no-untyped-def]
        msg = f"Cannot read {path}: ENOENT"
        result = sanitize_log_message(msg)
        # The prefix is preserved; the rest is redacted.
        assert "[REDACTED]" in result
        assert "secret" not in result
        assert "private" not in result

    def test_redacts_bare_mac(self):  # type: ignore[no-untyped-def]
        msg = "Bluetooth open failed for AA:BB:CC:DD:EE:FF ch=1"
        result = sanitize_log_message(msg)
        assert "AA:BB:CC:" in result
        assert "DD:EE:FF" not in result

    def test_redacts_image_field(self):  # type: ignore[no-untyped-def]
        # Verify the new `image`/`url`/`path` field names are in the default list.
        msg = "fetch failed image=/config/secret.png url=https://x.example/p"
        result = sanitize_log_message(msg)
        assert "[REDACTED]" in result
        assert "secret" not in result


# ---------------------------------------------------------------------------
# Timeout + constants.
# ---------------------------------------------------------------------------


class TestTimeoutValidation:
    def test_valid(self):  # type: ignore[no-untyped-def]
        assert validate_timeout(5.0) == 5.0

    def test_zero(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a positive number"):
            validate_timeout(0)

    def test_too_large(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="cannot exceed"):
            validate_timeout(400)


class TestSecurityConstants:
    def test_max_constants(self):  # type: ignore[no-untyped-def]
        assert MAX_TEXT_LENGTH == 10000
        assert MAX_QR_DATA_LENGTH == 2000
        assert MAX_BARCODE_LENGTH == 100
        assert MAX_FEED_LINES == 50
        assert MAX_BEEP_TIMES == 10

    def test_extension_set(self):  # type: ignore[no-untyped-def]
        assert ".png" in VALID_IMAGE_EXTENSIONS
        assert ".svg" not in VALID_IMAGE_EXTENSIONS
