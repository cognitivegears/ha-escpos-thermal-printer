# Network (TCP/IP) Printers

For printers with Ethernet or WiFi.

## Connection settings

| Setting | Description | Default |
|---------|-------------|---------|
| Host | IP address or hostname | Required |
| Port | TCP port | 9100 |
| Timeout | Connect timeout (seconds) | 4.0 |
| Printer Profile | Your printer model | Generic (no profile) |

## Finding your printer's IP

Most thermal printers can print a network status page:

1. Power off the printer.
2. Hold the feed button while powering on.
3. The printout shows the IP and network config.

Alternatively, check your router's DHCP client list.

**Tip**: assign a static IP (or DHCP reservation). If the printer's address does change, update it in place via **Settings → Devices & services → ESC/POS Thermal Printer → your printer → Reconfigure**; your entities and automations survive intact (no need to delete and re-add).

## Automatic discovery

Home Assistant listens for DHCP announcements matching known thermal-printer
hostname patterns: `tm-*` for Epson TM-series (the vendor's own device
naming convention) and `rongta_*` for Rongta. A candidate is probed on
port 9100 before it's offered; `tm-*` matches additionally have to answer
an ESC/POS `GS I` identity query, since port 9100 is also the default for
Prometheus `node_exporter` and other non-printer services. Anything that
doesn't pass these checks is ignored silently, no notification, no partial
setup screen.

A discovered printer shows up under **Settings → Devices & Services →
Discovered**; accepting it prefills the host and preselects the matching
printer profile.

Separately from discovery, every network setup and reconfigure queries the
printer directly with `GS I`. Printers that answer (mostly genuine Epson
hardware) get their real manufacturer/model shown on the device page and
prefilled into the calibration wizard's share-link model field. Printers
that don't answer (most clones) behave exactly as before. Reconfigure
re-runs the query: if the printer's address didn't change and it simply
fails to answer this time, the previously detected identity is kept; if
the address changed, or a fresh answer comes back, the stored identity is
replaced (or cleared, if the new address doesn't answer either).

## Paper status sensor

Network printers get a `sensor.<printer>_paper_status` entity reporting `ok`, `low`, or `out`, backed by the ESC/POS real-time paper-sensor query (`DLE EOT 4`). It polls on Home Assistant's standard entity cadence and automatically skips a poll while a print is in flight. If the printer doesn't answer the query (not all firmwares implement it) or is unreachable, the sensor shows unavailable. See [automations.md](automations.md) for a paper-low notification example.

## Multiple network printers

Add the integration once per printer. Each gets its own device, binary sensor, and notify entity. See [multi-printer.md](multi-printer.md) for targeting in service calls.

## Common issues

- **"Cannot connect"**: verify the IP via `ping`/`telnet <ip> 9100`.
- **Connection works sometimes**: DHCP lease churn or sleep mode; assign a static IP.
- **"Connection refused"**: another app holds the printer, or printer is in an error state (paper out, cover open).

See [troubleshooting.md](troubleshooting.md#network-issues) for more.
