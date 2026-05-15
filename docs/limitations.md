# Known Limitations

## All connection types

- **One queued operation per printer.** Each adapter holds an `asyncio.Lock`; service calls to the same printer serialize. Concurrent prints to the same device wait their turn.
- **Image width is capped at 512 pixels.** Larger images are auto-resized; truly large files may be rejected.
- **No print preview.** Output is unbuffered ESC/POS — what you send is what prints.
- **Print quality** depends on the printer's hardware density setting and paper. Not adjustable from the integration.

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
