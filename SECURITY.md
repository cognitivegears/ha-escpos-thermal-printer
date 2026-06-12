# Security Guidelines for HA ESCPOS Thermal Printer Integration

## Overview

This document outlines the security measures and best practices implemented in the HA ESCPOS Thermal Printer integration to ensure secure operation and protect against common vulnerabilities.

## Security Features

### 1. Input Validation and Sanitization

The integration implements input validation to prevent injection attacks and
resource exhaustion. Validation is centralized in
`custom_components/escpos_printer/security.py` and reused by every service
schema (Bronze quality-scale `action-setup` rule):

- **Service-level schemas** (voluptuous) — every action registered via
  `hass.services.async_register(..., schema=...)`. REST / WebSocket /
  Python-script callers go through the same validation as the UI selectors.
- **Text input** — length cap (`MAX_TEXT_LENGTH = 10000`), control characters
  stripped.
- **Image URLs** — `validate_image_url` rejects non-`http(s)` schemes,
  embedded credentials (`https://user:pass@host/`), IDN/punycode hostnames,
  and non-default ports. `validate_image_url_and_resolve` additionally
  resolves the hostname and **rejects private, loopback, link-local,
  reserved, multicast, and unspecified IPs** (defends against SSRF to
  RFC1918 networks, `127.0.0.1`, `::1`, and cloud-metadata endpoints like
  `169.254.169.254`). HTTP redirects are followed manually and each
  redirect target is re-validated. A per-printer **"Allow local image
  URLs"** opt-in (default off) relaxes the private/loopback block and the
  port allowlist for that printer; the always-dangerous ranges remain
  blocked even when enabled — cloud-metadata (`169.254.169.254` and AWS
  IMDSv6 `fd00:ec2::254`, the `_ALWAYS_BLOCKED_HOSTS` denylist),
  link-local, multicast, reserved, and unspecified. Enabling it turns that
  printer's `print_image_url` into an unauthenticated LAN-reach primitive
  (the service has no per-user authorization), so enable it only where the
  callers are trusted.
- **Local image paths** — `Path.resolve(strict=True)` dereferences
  symlinks before the extension / size / allowlist checks; the final
  `open()` uses `O_NOFOLLOW` to defeat TOCTOU swaps. Paths outside
  `allowlist_external_dirs` are **rejected** (no warn-but-read).
- **Camera / image entity sources** — the calling user's permissions are
  checked via `user.permissions.check_entity(entity_id, POLICY_READ)`;
  denied users receive `Unauthorized` (HTTP 403 from the WebSocket / REST
  API). Internal calls without a `user_id` and admins bypass.
- **Base64 data URIs** — input length capped *before* regex/decoding
  (no OOM on a 200 MB base64 string); subtype pinned to
  `png|jpe?g|gif|bmp|tiff|webp` (no SVG / XML decoder reach).
- **Pillow** — a decompression-bomb guard is enforced per-decode against
  the image header dimensions (before any full-bitmap allocation),
  scoped to this integration so Pillow's process-global limit is left
  untouched for other Home Assistant consumers; `Image.open` is invoked
  with a pinned `formats=` allow-list.
- **Numeric input** — every numeric parameter validated within safe
  bounds (`MAX_FEED_LINES`, `IMAGE_FRAGMENT_MIN/MAX`, etc.) declared in
  `security.py` and reused by the voluptuous schemas in
  `services/schemas.py`.

### 2. Security Scanning Tools

The project includes automated security scanning as part of the development and CI/CD process:

- **Bandit**: Performs static analysis to detect common security issues in Python code
- **pip-audit**: Audits installed packages for known vulnerabilities
- **Ruff Security Rules** (`S` category): Security-focused linting rules run as part of the main lint job

### 3. Secure Coding Practices

#### Input Validation

```python
# Example of secure input validation
from .security import validate_text_input, validate_numeric_input

text = validate_text_input(user_input)
feed_lines = validate_numeric_input(feed_param, 0, MAX_FEED_LINES, "feed lines")
```

#### Secure Logging

```python
# Example of secure logging that prevents information disclosure
from .security import sanitize_log_message

log_msg = sanitize_log_message(
    f"Processing data: {data}",
    ["password", "token", "key"]
)
_LOGGER.debug(log_msg)
```

`sanitize_log_message` redacts:

- `field=value` pairs whose field name appears in the default sensitive
  list (`password`, `token`, `key`, `secret`, `data`, `text`, `address`,
  `mac`, `alias`, `url`, `path`, `host`, `image`, `source`).
- URL userinfo (`scheme://user:pass@host/...` → `scheme://[REDACTED]@host/...`).
- Filesystem paths under HA's standard mount points (`/config/`,
  `/media/`, `/share/`, `/ssl/`, `/addon_configs/`, `/data/`) — preserves
  the prefix, redacts the rest.
- Bluetooth MAC addresses (preserves the 3-octet OUI for vendor lookups,
  redacts the device-specific portion as personal data under GDPR).

#### Resource Limits

- Maximum text length: 10,000 characters
- Maximum QR data length: 2,000 characters
- Maximum barcode data length: 100 characters
- Maximum image download size: 10 MB (also the **decoded** cap for base64
  data URIs)
- Maximum decoded pixel count: 20 million per decode (40 million with
  `auto_resize`, since the source is downscaled after decode)
- Maximum processed image height: 8192 px
- Maximum image slices per print: 64 (avoids paper-DoS via tall ribbons)
- Maximum feed lines: 50
- Maximum beep repetitions: 10

## Threat Model & Mitigations

This section documents the **current** security posture (post-Phase 2
hardening, 0.7.0+). Items previously listed under "Known Limitations"
have moved to "Mitigated" with the implementation pointer.

### Mitigated

- **DNS rebinding for HTTP image fetch** — The URL validator resolves
  the hostname and returns the address set; the fetcher then builds a
  per-request `aiohttp` session with `_StaticResolver`
  (`image_sources._StaticResolver`) pinned to those addresses. A 0-TTL
  hostile DNS server cannot swap public → private between validation
  and connect. Each redirect hop runs through the validator again and
  gets a fresh pin. **CWE-918 / CWE-350.**
- **TOCTOU symlink swap on local-file reads** — `Path.resolve()`
  dereferences symlinks during validation; the file is then opened
  with `O_NOFOLLOW` (`security.open_local_image_no_follow`,
  `open_local_font_no_follow`) so a symlink swap between stat and
  open is also defeated. **CWE-59 / CWE-367.**
- **TOCTOU symlink swap on preview writes** — Preview-service file
  writes use `O_NOFOLLOW | O_TRUNC | 0o600` via
  `security.write_file_no_follow`; an attacker who plants a symlink
  under tempdir between path-validation and image-save cannot redirect
  the write into an arbitrary file. **CWE-59 / CWE-367.**
- **Preview `output_path` privilege escalation** — `preview_image`,
  `preview_box`, `preview_table` now restrict user-supplied
  `output_path` to the system tempdir. Previously a non-admin HA user
  could call `preview_image` with
  `output_path: /config/configuration.yaml` and clobber it with
  rendered PNG bytes. **CWE-862 / CWE-552.**
- **IDN homograph bypass** — `validate_image_url` now IDNA-encodes
  raw-Unicode hostnames before the `xn--` substring check, so both
  `例え.テスト` and `xn--r8jz45g.xn--zckzah` are rejected. **CWE-918.**
- **Exception-message information disclosure** — `services/_handler_utils.py`
  `_for_each_target` routes every service handler's exception through
  `sanitize_log_message` so USB serials, BT MACs, and filesystem
  paths from pyusb/pyserial/python-escpos do not leak into the HA
  Frontend toast. **CWE-209 / CWE-532.**
- **Font path narrowed trust** — `security.validate_font_path_with_fonts_dir`
  accepts paths under HA's `allowlist_external_dirs` OR under
  `<config>/fonts/` (auto-created on integration setup). The
  `<config>/fonts/` widening is the only narrowing; all other
  path-based services use the standard allowlist.
- **Cancel-during-cleanup paper hang** — `print_text_with_image`
  wraps its cleanup `_apply_cut_and_feed` in `asyncio.shield` so a
  second cancellation mid-flush cannot leave paper attached.

### Residual / Known limitations

- **Trust boundary** — any HA user who can call
  `escpos_printer.print_image` or `notify.<printer>` can print to
  your physical paper roll. Restrict service exposure via HA's
  standard scripts / scenes / Lovelace card permissions for shared
  installations.
- **ESC/POS protocol bytes in printed content** — `validate_text_input`
  strips C0 control characters but not all printable ESC/POS escape
  sequences. If a downstream POS scanner consumes the receipt as
  data (rather than a human reading paper), additional sanitization
  may be warranted.
- **Camera / image entity authorization** — `_check_user_can_read_entity`
  forwards `ServiceCall.context` through every image source resolver
  so a non-admin user invoking `print_camera_snapshot` /
  `print_image_entity` is blocked from cameras / image entities they
  cannot read. HA admins bypass entity permissions by design; admin
  users can print any camera regardless.
- **Blueprint template safety** — the `variables:` block of every
  shipped blueprint is rendered through HA's sandboxed Jinja
  environment. Tests in `tests/test_blueprints_template_safety.py`
  pin this and include a regression canary asserting that an unsafe
  `list.append()` template raises. Coverage is `variables:`-only;
  `data:` blocks are not sandbox-rendered (this matches HA core
  behaviour).

## Security Configuration

### Bandit

Bandit runs in CI as `bandit -r custom_components/escpos_printer -lll`. The
`-lll` flag fails the build only on HIGH-severity findings; LOW/MEDIUM
findings appear in the JSON report uploaded as SARIF. Project-specific
ignores live in `pyproject.toml` under `[tool.ruff.lint] ignore` for the
flake8-bandit (`S`) rule family.

### Ruff Security Rules (pyproject.toml)

```toml
[tool.ruff.lint]
select = [
    "S",      # flake8-bandit (security)
    # ... other rules
]
```

The `S` ruleset runs as part of the main `ruff check .` invocation in
`validate.yml`; there is no separate security-only ruff pass.

## CI/CD Security Integration

### GitHub Actions Security Workflow

The project includes automated security scanning in CI/CD:

1. **Dependency Scanning**: Runs on every push and pull request
2. **Code Security Analysis**: Static analysis for security vulnerabilities
3. **Automated Reporting**: Security findings are reported and can block merges
4. **Scheduled Scans**: Weekly comprehensive security scans

### Running Security Scans Locally

```bash
# Python security linting (HIGH-severity gate)
bandit -r custom_components/escpos_printer -lll

# Dependency audit
pip-audit
```

## Security Considerations

### Network Security

- All network communications use timeout limits
- Image downloads are restricted to HTTP/HTTPS protocols
- No sensitive data is transmitted in URLs or headers

### File System Security

- Local file access is restricted to allowed image formats
- Path traversal attacks are prevented through validation
- Temporary files are properly cleaned up

### Resource Protection

- Input size limits prevent resource exhaustion attacks
- Rate limiting considerations for service calls
- Memory usage is monitored and limited

## Vulnerability Reporting

If you discover a security vulnerability in this integration:

1. **Do not** create a public GitHub issue.
2. Report it privately via [GitHub Security Advisories](https://github.com/cognitivegears/ha-escpos-thermal-printer/security/advisories/new).
3. Include detailed information about the vulnerability and a reproduction case.
4. Allow reasonable time for response and a fix before public disclosure.

## Security Best Practices for Users

### Configuration Security

- Use strong, unique passwords for printer access
- Restrict network access to printers when possible
- Regularly update printer firmware
- Monitor printer access logs

### Operational Security

- Limit user access to printing services
- Implement logging and monitoring
- Regularly review and rotate credentials
- Keep the integration and dependencies updated

### Network Security

- Use firewalls to restrict printer network access
- Implement VPNs for remote printer access
- Monitor network traffic for anomalies
- Use HTTPS for web-based image sources

## Security Testing

### Unit Tests for Security

```python
def test_input_validation():
    # Test input validation functions
    with pytest.raises(HomeAssistantError):
        validate_text_input("x" * 10001)  # Exceeds max length
```

### Integration Tests for Security

```python
def test_path_traversal_protection():
    # Test path traversal protection via the read-side O_NOFOLLOW opener
    # (`security.open_local_image_no_follow`), the same primitive used by
    # `image_sources._resolve_local` to read user-supplied image paths.
    with pytest.raises(HomeAssistantError):
        validate_local_image_path("../../../etc/passwd")
```

## Compliance and Standards

This integration follows security best practices aligned with:

- **OWASP Top 10**: Protection against common web application vulnerabilities
- **Python Security Best Practices**: Following PEP 508 and secure coding guidelines
- **Home Assistant Security Guidelines**: Compliance with HA integration security requirements

## Maintenance and Updates

### Regular Security Updates

- Dependencies are regularly updated to address security vulnerabilities
- Security scans are run weekly to identify new issues
- Critical security patches are applied promptly

### Security Monitoring

- Automated vulnerability scanning in CI/CD
- Regular code reviews with security focus
- Dependency monitoring for security advisories

## References

- [OWASP Python Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Python_Security_Cheat_Sheet.html)
- [Python Security Best Practices](https://bestpractices.coreinfrastructure.org/en/projects/221)
- [Home Assistant Security Guidelines](https://developers.home-assistant.io/docs/development_security)
- [Bandit Documentation](https://bandit.readthedocs.io/)
