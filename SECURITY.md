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
  redirect target is re-validated.
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
- **Pillow** — `Image.MAX_IMAGE_PIXELS` set process-globally so
  decompression bombs raise deterministically; `Image.open` is invoked
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
- Maximum decoded pixel count: 20 million (`Image.MAX_IMAGE_PIXELS`)
- Maximum processed image height: 8192 px
- Maximum image slices per print: 64 (avoids paper-DoS via tall ribbons)
- Maximum feed lines: 50
- Maximum beep repetitions: 10

## Known Limitations

These deserve explicit mention so deployers understand the threat model:

- **Trust boundary** — any HA user who can call `escpos_printer.print_image`
  or `notify.<printer>` can print to your physical paper roll. Restrict
  service exposure via HA's standard scripts / scenes / Lovelace card
  permissions for shared installations.
- **SSRF on out-of-process resolvers** — between our `getaddrinfo`-based
  IP check and the actual fetch by `httpx` / `aiohttp`, there is a
  small TOCTOU window. Sophisticated DNS-rebinding attacks against this
  window are not fully mitigated; pinning to the resolved IP would
  require a custom transport and break SNI. The validation rejects
  the common case (a URL whose hostname directly resolves to a private
  address).
- **ESC/POS protocol bytes in printed content** — `validate_text_input`
  strips C0 control characters but not all printable ESC/POS escape
  sequences. If a downstream POS scanner consumes the receipt as data
  (rather than a human reading paper), additional sanitization may be
  warranted.
- **Camera / image authorization** — see `image_sources.py` for the
  permission check pattern. Bear in mind HA admins bypass entity
  permissions by design; admin users can print any camera regardless.

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
    # Test path traversal protection
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
