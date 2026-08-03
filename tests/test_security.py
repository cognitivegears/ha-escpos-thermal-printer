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

    @pytest.mark.parametrize(
        "payload",
        ["12345\x00\x1bp", "ab\x1dcd", "foo\x00bar", "x\x1bX", "\x10dle"],
    )
    def test_validate_barcode_data_rejects_control_bytes(self, payload):  # type: ignore[no-untyped-def]
        # ESC/GS/NUL/C0 bytes could terminate the GS k barcode frame early
        # and inject raw ESC/POS commands (cash-drawer kick, codepage
        # change). They must be rejected, not stripped.
        with pytest.raises(HomeAssistantError, match="control characters"):
            validate_barcode_data(payload, "CODE128")


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

    @pytest.mark.parametrize(
        "url",
        [
            # Pre-encoded (xn-- form) — the original test case.
            "https://xn--paypa-yfa.com/x.png",
            # Raw-Unicode hostnames (T-H3) — S-M6 fix added the
            # IDNA-encode-then-check branch so these are caught too.
            # The previous `"xn--" in hostname.lower()` substring test
            # missed these because urlparse does not IDNA-encode.
            "https://例え.テスト/x.png",
            "https://пример.рф/x.png",
        ],
    )
    def test_validate_image_url_rejects_idn(self, url):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="IDN"):
            validate_image_url(url)

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

    def test_strict_port_rejection_points_at_toggle(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="Allow local image URLs"):
            validate_image_url("http://example.com:5000/x.png")

    @pytest.mark.parametrize(
        "url",
        [
            "http://192.168.1.10:5000/x.png",  # Frigate
            "http://example.com:8080/x.png",  # camera
            "https://homeassistant.local:8123/x.png",  # HA itself
        ],
    )
    def test_validate_image_url_allows_non_default_ports_with_allow_local(  # type: ignore[no-untyped-def]
        self, url
    ):
        # The opt-in lifts the default-port allowlist; the address-level
        # SSRF check (validate_image_url_and_resolve) is the real boundary.
        assert validate_image_url(url, allow_local=True) == url

    @pytest.mark.parametrize("allow_local", [False, True])
    def test_validate_image_url_rejects_out_of_range_port(self, allow_local):  # type: ignore[no-untyped-def]
        # Accessing urlparse().port range-checks lazily; both modes must
        # surface a clean HomeAssistantError, never a bare ValueError.
        with pytest.raises(HomeAssistantError, match="port"):
            validate_image_url("https://example.com:99999/x.png", allow_local=allow_local)


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
            "switch.front",  # wrong domain
            "camera.",  # missing object id
            "camera",  # missing dot
            "camera.Front-Door",  # uppercase + dash
            "camera." + "a" * 65,  # exceeds length cap (S-M6)
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
        assert MAX_BEEP_TIMES == 9

    def test_text_effects_max_constants(self):  # type: ignore[no-untyped-def]
        """T-M3: pin the text-effects bounds added in the 0.7 branch.

        These caps protect against paper-waste / executor-pool DoS via
        large legal-shape inputs. Locking the numeric values here gives
        regression evidence when someone "just bumps the constant".
        """
        from custom_components.escpos_printer.security import (
            MAX_BOX_WIDTH,
            MAX_FONT_SIZE_BYTES,
            MAX_RENDER_HEIGHT_PX,
            MAX_RENDER_PIXELS,
            MAX_SEPARATOR_REPEAT,
            MAX_TABLE_CELL_LENGTH,
            MAX_TABLE_COLS,
            MAX_TABLE_ROWS,
        )

        assert MAX_BOX_WIDTH == 200
        assert MAX_TABLE_ROWS == 200
        assert MAX_TABLE_COLS == 12
        assert MAX_TABLE_CELL_LENGTH == 1000
        assert MAX_SEPARATOR_REPEAT == 10
        assert MAX_RENDER_PIXELS == 5_000_000
        assert MAX_RENDER_HEIGHT_PX == 8192
        assert MAX_FONT_SIZE_BYTES == 16 * 1024 * 1024

    def test_extension_set(self):  # type: ignore[no-untyped-def]
        assert ".png" in VALID_IMAGE_EXTENSIONS
        assert ".svg" not in VALID_IMAGE_EXTENSIONS


# ---------------------------------------------------------------------------
# Text-effects validators: validate_font_path / validate_rows.
# ---------------------------------------------------------------------------


class TestFontPathValidation:
    def test_validate_font_path_accepts_bundled_font(self):  # type: ignore[no-untyped-def]
        from pathlib import Path

        from custom_components.escpos_printer.security import validate_font_path

        bundled = (
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "escpos_printer"
            / "fonts"
            / "DejaVuSansMono.ttf"
        )
        resolved = validate_font_path(str(bundled))
        assert resolved.exists()
        assert resolved.suffix.lower() == ".ttf"

    def test_validate_font_path_rejects_bad_extension(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_font_path

        bad = tmp_path / "not-a-font.png"
        bad.write_bytes(b"\x89PNG fake")
        with pytest.raises(HomeAssistantError, match="not allowed"):
            validate_font_path(str(bad))

    def test_validate_font_path_rejects_nonexistent(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_font_path

        with pytest.raises(HomeAssistantError, match="does not exist"):
            validate_font_path("/nonexistent/path/does-not-exist.ttf")

    def test_validate_font_path_rejects_non_string(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_font_path

        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_font_path(42)  # type: ignore[arg-type]

    def test_validate_font_path_rejects_oversize_file(self, tmp_path):  # type: ignore[no-untyped-def]
        """A font file larger than MAX_FONT_SIZE_BYTES is rejected up-front.

        Phase 2 S-M3: defends against an attacker-supplied multi-GB
        ``font_path`` that would otherwise pin FreeType's parser in
        seconds of allocation work.
        """
        from custom_components.escpos_printer.security import (
            MAX_FONT_SIZE_BYTES,
            validate_font_path,
        )

        big = tmp_path / "huge.ttf"
        with open(big, "wb") as fh:
            fh.seek(MAX_FONT_SIZE_BYTES + 1)
            fh.write(b"\0")
        with pytest.raises(HomeAssistantError, match="too large"):
            validate_font_path(str(big))

    def test_validate_font_path_rejects_symlinked_input(self, tmp_path):  # type: ignore[no-untyped-def]
        """A user-supplied symlink to a font is rejected even if the target is valid.

        Defeats the "drop a symlink in /config/fonts/ pointing at
        attacker-writable bytes" trick — the validator inspects the raw
        path before ``Path.resolve`` follows the link.
        """
        from custom_components.escpos_printer.security import validate_font_path

        target = tmp_path / "real.ttf"
        target.write_bytes(b"OTTO")  # any bytes; we only test the symlink check
        link = tmp_path / "via-link.ttf"
        link.symlink_to(target)
        with pytest.raises(HomeAssistantError, match="symlink"):
            validate_font_path(str(link))

    def test_open_local_font_no_follow_rejects_symlink_swap(self, tmp_path):  # type: ignore[no-untyped-def]
        """``open_local_font_no_follow`` refuses to open a path that became a symlink.

        Regression for the TOCTOU between ``validate_font_path`` and
        ``ImageFont.truetype``: even if a path was a regular file at
        validate time, the open MUST fail (rather than silently follow)
        if it has since been replaced by a symlink.
        """
        from custom_components.escpos_printer.security import open_local_font_no_follow

        decoy = tmp_path / "decoy.bin"
        decoy.write_bytes(b"PWN!")
        link_at_validated_path = tmp_path / "font.ttf"
        link_at_validated_path.symlink_to(decoy)
        with pytest.raises(OSError):
            open_local_font_no_follow(link_at_validated_path)

    async def test_validate_font_path_allowlist_checked_before_existence(  # type: ignore[no-untyped-def]
        self, hass, monkeypatch
    ):
        """A nonexistent path outside the allowlist must yield the allowlist error.

        The ``hass`` allowlist decision runs before the existence check,
        so a caller outside the allowlist can't use the distinct "does not
        exist" error as an oracle for arbitrary host paths.
        """
        from custom_components.escpos_printer.security import validate_font_path

        monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: False)
        with pytest.raises(HomeAssistantError, match="allowlist"):
            validate_font_path("/nonexistent/outside/font.ttf", hass=hass)

    async def test_validate_font_path_allowlist_checked_before_oversize(  # type: ignore[no-untyped-def]
        self, hass, monkeypatch, tmp_path
    ):
        """An oversized file outside the allowlist must yield the allowlist error, not 'too large'."""
        from custom_components.escpos_printer.security import (
            MAX_FONT_SIZE_BYTES,
            validate_font_path,
        )

        monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: False)
        big = tmp_path / "huge.ttf"
        with open(big, "wb") as fh:
            fh.seek(MAX_FONT_SIZE_BYTES + 1)
            fh.write(b"\0")
        with pytest.raises(HomeAssistantError, match="allowlist"):
            validate_font_path(str(big), hass=hass)

    async def test_validate_font_path_with_fonts_dir_rejects_sibling_dir(  # type: ignore[no-untyped-def]
        self, hass, monkeypatch
    ):
        """A path under a sibling dir (``<config>/fonts-evil/``) must not be accepted.

        Guards against a future ``startswith`` simplification of the
        fonts-dir trust check, which would incorrectly treat
        ``<config>/fonts-evil/...`` as if it were under ``<config>/fonts/``.
        """
        from pathlib import Path

        from custom_components.escpos_printer.security import (
            validate_font_path_with_fonts_dir,
        )

        monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: False)
        evil_dir = Path(hass.config.path("fonts-evil"))
        evil_dir.mkdir(parents=True, exist_ok=True)
        bundled = (
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "escpos_printer"
            / "fonts"
            / "DejaVuSansMono.ttf"
        )
        evil_font = evil_dir / "x.ttf"
        evil_font.write_bytes(bundled.read_bytes())
        with pytest.raises(HomeAssistantError, match="allowlist"):
            validate_font_path_with_fonts_dir(str(evil_font), hass)

    async def test_validate_font_path_with_fonts_dir_rechecks_after_second_resolve(  # type: ignore[no-untyped-def]
        self, hass, monkeypatch, tmp_path
    ):
        """TOCTOU: a symlink swapped between the trust precheck and
        ``validate_font_path``'s own resolve must still be rejected.

        The precheck sees a path inside ``<config>/fonts/``; the second
        resolve (``validate_font_path``'s internal ``Path.resolve``)
        simulates the swap by returning a path outside any trusted
        location. The trust decision must be re-checked against that
        second-resolve result.
        """
        from pathlib import Path

        from custom_components.escpos_printer import security
        from custom_components.escpos_printer.security import (
            validate_font_path_with_fonts_dir,
        )

        fonts_dir = Path(hass.config.path("fonts"))
        fonts_dir.mkdir(parents=True, exist_ok=True)
        good = fonts_dir / "trusted.ttf"
        good.write_bytes(b"OTTO")
        outside = tmp_path / "outside" / "evil.ttf"

        monkeypatch.setattr(hass.config, "is_allowed_path", lambda p: False)
        monkeypatch.setattr(security, "validate_font_path", lambda *a, **kw: outside)
        with pytest.raises(HomeAssistantError, match="allowlist"):
            validate_font_path_with_fonts_dir(str(good), hass)


class TestWriteFileNoFollow:
    """Regression tests for ``security.write_file_no_follow`` (S-M2, T-H1).

    Preview-service file writes go through this primitive so a co-resident
    attacker cannot plant a symlink under tempdir between path-validation
    and write to redirect the output into an arbitrary file (the symmetric
    defense to the read-side ``open_local_font_no_follow``).
    """

    def test_write_file_no_follow_rejects_symlink_leaf(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import write_file_no_follow

        decoy = tmp_path / "decoy.txt"
        decoy.write_text("untouched")
        link = tmp_path / "out.txt"
        link.symlink_to(decoy)
        with pytest.raises(OSError):  # ELOOP from O_NOFOLLOW
            write_file_no_follow(str(link), b"PWN!")
        # The decoy must be unmodified — proves the write was blocked.
        assert decoy.read_text() == "untouched"

    def test_write_file_no_follow_writes_regular_file(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import write_file_no_follow

        out = tmp_path / "out.bin"
        write_file_no_follow(str(out), b"abc")
        assert out.read_bytes() == b"abc"
        # Owner-only mode (0o600) so a co-resident attacker cannot read
        # an in-flight preview, only the HA process owner.
        assert oct(out.stat().st_mode)[-3:] == "600"

    def test_write_file_no_follow_truncates_existing(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import write_file_no_follow

        out = tmp_path / "existing.bin"
        out.write_bytes(b"longer existing content")
        write_file_no_follow(str(out), b"abc")
        # O_TRUNC must replace the file, not append.
        assert out.read_bytes() == b"abc"


class TestValidateRows:
    def test_rejects_non_list(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_rows

        with pytest.raises(HomeAssistantError, match="list of rows"):
            validate_rows("not a list")

    def test_rejects_empty_rows(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_rows

        with pytest.raises(HomeAssistantError, match="at least one row"):
            validate_rows([])

    def test_rejects_too_many_rows(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import MAX_TABLE_ROWS, validate_rows

        oversize = [["a"]] * (MAX_TABLE_ROWS + 1)
        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            validate_rows(oversize)

    def test_rejects_too_many_columns(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import MAX_TABLE_COLS, validate_rows

        oversize_row = ["x"] * (MAX_TABLE_COLS + 1)
        with pytest.raises(HomeAssistantError, match="row width"):
            validate_rows([oversize_row])

    def test_coerces_non_string_cells(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_rows

        out = validate_rows([[1, 2.5, None, "x"]])
        assert out == [["1", "2.5", "", "x"]]

    def test_strips_control_characters_from_cells(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_rows

        out = validate_rows([["a\x00b\x07c"]])
        # validate_text_input strips C0 control characters except CR/LF/HT.
        assert out == [["abc"]]


class TestIsAllowedAddress:
    """The opt-in ``allow_local`` relaxation of the SSRF address filter.

    Strict mode (``allow_local=False``) is the historical "public only"
    behavior. Permissive mode allows private/LAN/loopback while keeping
    the genuinely dangerous ranges (cloud-metadata link-local, multicast,
    reserved, unspecified) blocked.
    """

    @pytest.mark.parametrize(
        "addr",
        ["93.184.216.34", "8.8.8.8", "2606:2800:220:1:248:1893:25c8:1946"],
    )
    def test_public_allowed_in_both_modes(self, addr):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _is_allowed_address

        assert _is_allowed_address(addr, allow_local=False) is True
        assert _is_allowed_address(addr, allow_local=True) is True

    @pytest.mark.parametrize(
        "addr",
        ["10.0.0.5", "192.168.1.50", "172.16.0.1", "127.0.0.1", "::1", "fc00::1"],
    )
    def test_private_loopback_only_with_allow_local(self, addr):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _is_allowed_address

        assert _is_allowed_address(addr, allow_local=False) is False
        assert _is_allowed_address(addr, allow_local=True) is True

    @pytest.mark.parametrize(
        "addr",
        [
            "169.254.169.254",  # IMDSv4 cloud metadata — the whole point of keeping it blocked
            "169.254.1.1",
            "fe80::1",  # IPv6 link-local
            "fd00:ec2::254",  # AWS IMDSv6 — a ULA that the private grant would otherwise allow
            "224.0.0.1",  # multicast
            "0.0.0.0",  # unspecified
            "240.0.0.1",  # reserved
        ],
    )
    def test_dangerous_ranges_blocked_even_with_allow_local(self, addr):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _is_allowed_address

        assert _is_allowed_address(addr, allow_local=False) is False
        assert _is_allowed_address(addr, allow_local=True) is False

    @pytest.mark.parametrize(
        "addr",
        ["fd12:3456:789a::1", "fdce:1234::abcd", "fc00::1"],
    )
    def test_legitimate_ula_still_allowed_with_opt_in(self, addr):  # type: ignore[no-untyped-def]
        # The IMDSv6 block must be the *specific* metadata host, not the whole
        # ULA range — home IPv6 LANs legitimately use fc00::/7.
        from custom_components.escpos_printer.security import _is_allowed_address

        assert _is_allowed_address(addr, allow_local=False) is False
        assert _is_allowed_address(addr, allow_local=True) is True

    def test_unparseable_address_rejected(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _is_allowed_address

        assert _is_allowed_address("not-an-ip", allow_local=True) is False


# ---------------------------------------------------------------------------
# Diff-coverage top-up: non-string / edge-case branches on the small
# validators that were otherwise only exercised via their happy paths.
# ---------------------------------------------------------------------------


class TestNonStringGuards:
    """Every ``if not isinstance(value, str): raise`` guard, hit directly."""

    def test_validate_qr_data_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_qr_data(123)  # type: ignore[arg-type]

    def test_validate_barcode_data_rejects_non_string_code(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be strings"):
            validate_barcode_data(123, "CODE128")  # type: ignore[arg-type]

    def test_validate_barcode_data_rejects_whitespace_only(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="cannot be empty"):
            validate_barcode_data("   ", "CODE128")

    def test_validate_image_url_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_image_url(123)  # type: ignore[arg-type]

    def test_validate_base64_image_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_base64_image(None)  # type: ignore[arg-type]

    def test_validate_entity_id_for_domain_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_entity_id_for_domain(None, "camera")  # type: ignore[arg-type]

    def test_validate_dither_mode_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_dither_mode(123)  # type: ignore[arg-type]

    def test_validate_impl_mode_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_impl_mode(123)  # type: ignore[arg-type]

    def test_validate_local_path_sync_rejects_non_string(self):  # type: ignore[no-untyped-def]
        with pytest.raises(HomeAssistantError, match="must be a string"):
            _validate_local_path_sync(123)  # type: ignore[arg-type]

    def test_validate_font_path_rejects_too_long(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import (
            MAX_FONT_PATH_LENGTH,
            validate_font_path,
        )

        with pytest.raises(HomeAssistantError, match="exceeds maximum length"):
            validate_font_path("/" + "x" * (MAX_FONT_PATH_LENGTH + 1) + ".ttf")

    def test_validate_font_path_with_fonts_dir_rejects_non_string(self, hass):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_font_path_with_fonts_dir

        with pytest.raises(HomeAssistantError, match="must be a string"):
            validate_font_path_with_fonts_dir(123, hass)  # type: ignore[arg-type]


class TestUrlValidationEdgeCases:
    """Branches of ``validate_image_url`` not covered by the happy-path tests."""

    def test_rejects_malformed_ipv6_netloc(self):  # type: ignore[no-untyped-def]
        # A truncated IPv6 literal in the host makes `urlparse` itself raise
        # ValueError (before scheme/hostname checks even run).
        with pytest.raises(HomeAssistantError, match="Invalid URL format"):
            validate_image_url("http://[::1:80/x.png")

    def test_rejects_idn_hostname_that_fails_idna_encoding(self):  # type: ignore[no-untyped-def]
        # A non-ASCII hostname that already starts with the ACE prefix is
        # rejected by Python's idna codec with UnicodeError -- must surface
        # as a clean ServiceValidationError, not a bare UnicodeError.
        with pytest.raises(HomeAssistantError, match="Invalid IDN hostname"):
            validate_image_url("https://xn--\xe9.com/x.png")


class TestResolveHostnameSync:
    def test_raises_service_validation_error_on_unresolvable_host(self, monkeypatch):  # type: ignore[no-untyped-def]
        import socket

        from custom_components.escpos_printer.security import _resolve_hostname_sync

        def _boom(*_a, **_kw):  # type: ignore[no-untyped-def]
            raise OSError("Name or service not known")

        monkeypatch.setattr(socket, "getaddrinfo", _boom)
        with pytest.raises(HomeAssistantError, match="Could not resolve"):
            _resolve_hostname_sync("this-host-does-not-exist.invalid.example.", 80)


class TestValidateLocalPathSyncEdgeCases:
    def test_rejects_directory_masquerading_as_image(self, tmp_path):  # type: ignore[no-untyped-def]
        # A directory named "*.png" passes the extension check but must be
        # rejected once stat() reveals it isn't a regular file.
        dirpath = tmp_path / "dir.png"
        dirpath.mkdir()
        with pytest.raises(HomeAssistantError, match="not a regular file"):
            _validate_local_path_sync(str(dirpath))

    def test_rejects_path_through_non_directory_component(self, tmp_path):  # type: ignore[no-untyped-def]
        # Treating a regular file as if it were a directory component makes
        # `Path.resolve(strict=True)` raise `NotADirectoryError` (an OSError
        # subclass distinct from FileNotFoundError) -- must still surface as
        # a clean ServiceValidationError.
        regular = tmp_path / "not_a_dir.png"
        regular.write_bytes(b"\x89PNG\r\n\x1a\n")
        bogus = regular / "sub.png"
        with pytest.raises(HomeAssistantError, match="Cannot access image file"):
            _validate_local_path_sync(str(bogus))

    def test_rejects_when_stat_raises(self, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
        from pathlib import Path

        path = tmp_path / "img.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\n")

        def _boom(self):  # type: ignore[no-untyped-def]
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "stat", _boom)
        with pytest.raises(HomeAssistantError, match="Cannot access image file"):
            _validate_local_path_sync(str(path))


class TestBestEffortResolve:
    def test_falls_back_to_raw_string_on_unresolvable_path(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _best_effort_resolve

        # An embedded NUL byte makes `Path.resolve()` raise ValueError.
        raw = "bad\x00path"
        assert _best_effort_resolve(raw) == raw


class TestValidateFontPathEdgeCases:
    def test_rejects_path_through_non_directory_component(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_font_path

        regular = tmp_path / "not_a_dir.ttf"
        regular.write_bytes(b"OTTO")
        bogus = regular / "sub.ttf"
        with pytest.raises(HomeAssistantError, match="Cannot access font file"):
            validate_font_path(str(bogus))

    def test_rejects_directory_masquerading_as_font(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_font_path

        dirpath = tmp_path / "dir.ttf"
        dirpath.mkdir()
        with pytest.raises(HomeAssistantError, match="not a regular file"):
            validate_font_path(str(dirpath))

    def test_rejects_when_is_symlink_raises(self, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
        from pathlib import Path

        from custom_components.escpos_printer.security import validate_font_path

        path = tmp_path / "font.ttf"
        path.write_bytes(b"OTTO")

        def _boom(self):  # type: ignore[no-untyped-def]
            raise OSError("permission denied")

        monkeypatch.setattr(Path, "is_symlink", _boom)
        with pytest.raises(HomeAssistantError, match="Cannot access font file"):
            validate_font_path(str(path))

    def test_rejects_when_stat_raises(self, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
        from pathlib import Path

        from custom_components.escpos_printer.security import validate_font_path

        path = tmp_path / "font.ttf"
        path.write_bytes(b"OTTO")

        orig_stat = Path.stat

        def _boom(self):  # type: ignore[no-untyped-def]
            if self == path.resolve():
                raise OSError("permission denied")
            return orig_stat(self)

        monkeypatch.setattr(Path, "stat", _boom)
        with pytest.raises(HomeAssistantError, match="Cannot access font file"):
            validate_font_path(str(path))


class TestIsTrustedFontLocation:
    async def test_true_when_allowlisted(self, hass, monkeypatch):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _is_trusted_font_location

        monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: True)
        assert _is_trusted_font_location("/anything", hass) is True

    async def test_false_when_fonts_dir_unresolvable(self, hass, monkeypatch):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import _is_trusted_font_location

        monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: False)
        # An embedded NUL byte in the configured "fonts" path makes
        # `Path(...).resolve()` raise ValueError.
        monkeypatch.setattr(hass.config, "path", lambda *_a: "bad\x00fonts")
        assert _is_trusted_font_location("/some/font.ttf", hass) is False


class TestValidateRowsEdgeCases:
    def test_rejects_non_list_row(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import validate_rows

        with pytest.raises(HomeAssistantError, match="each row must be a list"):
            validate_rows([1, 2])

    def test_rejects_oversize_cell(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import MAX_TABLE_CELL_LENGTH, validate_rows

        with pytest.raises(HomeAssistantError, match="cell length exceeds maximum"):
            validate_rows([["x" * (MAX_TABLE_CELL_LENGTH + 1)]])


class TestSanitiseKvItemsEdgeCases:
    def test_rejects_oversize_cell(self):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import (
            MAX_TABLE_CELL_LENGTH,
            sanitise_kv_items,
        )

        with pytest.raises(HomeAssistantError, match="exceeds maximum"):
            sanitise_kv_items([["key", "x" * (MAX_TABLE_CELL_LENGTH + 1)]])


class TestReadNoFollowEdgeCases:
    def test_open_local_image_no_follow_rejects_directory(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import open_local_image_no_follow

        with pytest.raises(HomeAssistantError, match="not a regular file"):
            open_local_image_no_follow(tmp_path)

    def test_open_local_image_no_follow_rejects_oversize(self, tmp_path):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer.security import open_local_image_no_follow

        path = tmp_path / "img.png"
        path.write_bytes(b"\x89PNG\r\n\x1a\nEXTRA")
        with pytest.raises(HomeAssistantError, match="too large"):
            open_local_image_no_follow(path, max_bytes=4)


class TestBase64ImageEdgeCases:
    def test_rejects_invalid_padding(self):  # type: ignore[no-untyped-def]
        # "A" matches the base64-alphabet regex but is not valid base64
        # (wrong padding) -- must hit the binascii.Error decode branch.
        with pytest.raises(HomeAssistantError, match="Invalid base64 data"):
            validate_base64_image("data:image/png;base64,A")

    def test_rejects_decoded_payload_over_cap(self, monkeypatch):  # type: ignore[no-untyped-def]
        from custom_components.escpos_printer import security

        # Shrink the post-decode cap (but not the pre-decode input cap,
        # which is computed once at import time) so a ~2MB payload trips
        # the "too large" check *after* successful decoding.
        monkeypatch.setattr(security, "MAX_IMAGE_SIZE_MB", 1)
        raw = b"\x00" * (2 * 1024 * 1024)
        uri = "data:image/png;base64," + base64.b64encode(raw).decode()
        with pytest.raises(HomeAssistantError, match="too large"):
            security.validate_base64_image(uri)
