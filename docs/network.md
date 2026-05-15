# Network (TCP/IP) Printers

For printers with Ethernet or WiFi.

## Connection settings

| Setting | Description | Default |
|---------|-------------|---------|
| Host | IP address or hostname | Required |
| Port | TCP port | 9100 |
| Timeout | Connect timeout (seconds) | 4.0 |
| Printer Profile | Your printer model | Auto-detect |

## Finding your printer's IP

Most thermal printers can print a network status page:

1. Power off the printer.
2. Hold the feed button while powering on.
3. The printout shows the IP and network config.

Alternatively, check your router's DHCP client list.

**Tip**: assign a static IP (or DHCP reservation). Otherwise the printer may move IPs and the entry will go offline silently until reconfigured.

## Multiple network printers

Add the integration once per printer. Each gets its own device, binary sensor, and notify entity. See [multi-printer.md](multi-printer.md) for targeting in service calls.

## Common issues

- **"Cannot connect"** — verify the IP via `ping`/`telnet <ip> 9100`.
- **Connection works sometimes** — DHCP lease churn or sleep mode; assign a static IP.
- **"Connection refused"** — another app holds the printer, or printer is in an error state (paper out, cover open).

See [troubleshooting.md](troubleshooting.md#network-issues) for more.
