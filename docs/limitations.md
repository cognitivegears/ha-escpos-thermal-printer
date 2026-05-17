# Known Limitations

## All connection types

- **One queued operation per printer.** Each adapter holds an `asyncio.Lock`; service calls to the same printer serialize. Concurrent prints to the same device wait their turn.
- **Images auto-fit to the printer's profile width.** By default, images wider than the printer profile's maximum pixel width are resized down (with aspect ratio preserved). When the profile doesn't expose `media.width.pixels`, the integration falls back to **512 px** and logs a `WARNING` once per adapter — check `home-assistant.log` for `Printer profile does not expose media.width.pixels`. Set `image_width` on `print_image` to override. Images are never upscaled. See the [Images guide](images.md).
- **Image files are capped at 10 MB** (both for HTTP download and for decoded base64 data URIs).
- **Image processing caps.** Decoded images cannot exceed 20 M pixels (`Image.MAX_IMAGE_PIXELS`), 8192 rows of processed height, or 64 slices per print. These guard against decompression bombs and paper-DoS via tall ribbons.
- **Buffer overruns on tall images.** Chunked transmission (`fragment_height`, `chunk_delay_ms`) mitigates this; tune both per printer if you still see freezes or character dumps. Default `chunk_delay_ms` is 0 on Network / USB and 50 on Bluetooth.
- **No print preview.** Output is unbuffered ESC/POS — what you send is what prints.
- **Print quality** depends on the printer's hardware density setting and paper. Not adjustable from the integration.

## Security posture (image pipeline)

The image pipeline applies meaningful but bounded defenses; deployers
should understand what is and isn't enforced. Cross-linked from
[SECURITY.md](../SECURITY.md).

- **HTTP image fetches block private and loopback addresses.** URLs
  resolving to RFC1918 networks, `127.0.0.1`, `::1`, `169.254.169.254`
  (cloud metadata), or other non-public ranges are rejected. Redirects
  are followed manually and re-validated. There is a residual
  TOCTOU window between our DNS resolution and the actual fetch; DNS
  rebinding remains a partially-mitigated threat.
- **Embedded URL credentials are rejected.** `https://user:pass@host/`
  fails validation.
- **Local file paths must lie inside `allowlist_external_dirs`.** Paths
  outside are rejected (no warn-but-read). Symlinks are dereferenced
  during validation; the actual `open()` uses `O_NOFOLLOW`.
- **Camera / image entity reads check the caller's permissions.**
  Non-admin users without `POLICY_READ` on the named entity get
  `Unauthorized`. Admins bypass entity permissions by design.
- **Error messages from failed image loads are sanitized** —
  URL credentials, filesystem paths under HA mount points, and
  Bluetooth MACs are redacted from logs.
- **Trust boundary.** Any HA user who can call `escpos_printer.print_image`
  or `notify.<printer>` can print to your physical paper roll.
  Restrict service exposure for shared installations.

## Network printers

- **No keep-alive by default.** Connections reconnect per operation. Enabling Keep Alive trades latency for fragility when the printer goes offline.

## USB printers

- **No persistent USB connection.** Each operation reconnects. This avoids Linux device-pinning issues but adds ~50–200ms per print.
- **Permissions required.** On bare Linux you need a udev rule. HA OS handles this automatically.
- **Container pass-through required.** Plain Docker setups need `devices: - /dev/bus/usb:/dev/bus/usb` or a specific device bind.

## Bluetooth (RFCOMM) printers

- **Pair on the host first.** The integration does not initiate pairing. It only opens RFCOMM sockets to already-paired devices.
- **One client at a time.** RFCOMM is single-session. The integration auto-skips status probes during prints; aggressive `status_interval` settings hurt rather than help.
- **Plaintext over the air.** Bluetooth Classic SPP with no PIN or PIN `0000` is unencrypted. Don't route OTPs, 2FA codes, or other sensitive content to a BT printer.
- **`status_interval` floor of 60s.** Cheap BT printers beep on every connect; aggressive polling competes with in-flight prints. Set to 60s+ or 0.
- **Linux-only.** `AF_BLUETOOTH` is Linux-only. macOS / Windows HA installs cannot use this connection type natively.
- **Container caveats.** HA Container needs `--net=host` + `NET_ADMIN` + `NET_RAW` + `/run/dbus` mount. Or use the `socat` host-bridge fallback (see README).
- **Battery sensor only when bluez exposes it.** Most cheap thermal printers don't expose `org.bluez.Battery1`; the sensor stays unavailable for those.

## Codepage / character set

- **Not all profiles support all codepages.** The dropdown only shows codepages the selected profile advertises.
- **UTF-8 transcoding is best-effort.** `print_text_utf8` simplifies unsupported characters (curly quotes → straight, em-dash → `--`, accents stripped). Use the right codepage if you need fidelity.
