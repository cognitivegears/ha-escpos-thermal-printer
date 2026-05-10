#!/usr/bin/env python3
"""Standalone diagnostic script to test a network ESC/POS thermal printer.

Usage:
    python scripts/test_network_printer.py <ip_address> [--port PORT] [--profile PROFILE] [--timeout TIMEOUT]

Examples:
    python scripts/test_network_printer.py 192.168.1.100
    python scripts/test_network_printer.py 192.168.1.100 --profile TM-T20II
    python scripts/test_network_printer.py 192.168.1.100 --port 9100 --profile TM-T20II --timeout 10
"""

from __future__ import annotations

import argparse
import socket
import sys
import time
import traceback


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def test_dns_resolution(host: str) -> str | None:
    """Resolve hostname and return IP, or None on failure."""
    log(f"Resolving hostname '{host}' ...")
    try:
        ip = socket.gethostbyname(host)
        log(f"  Resolved to: {ip}")
        return ip
    except socket.gaierror as exc:
        log(f"  DNS resolution FAILED: {exc}")
        return None


def test_tcp_connection(host: str, port: int, timeout: float) -> bool:
    """Test raw TCP connectivity."""
    log(f"Testing TCP connection to {host}:{port} (timeout={timeout}s) ...")
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            elapsed_ms = (time.perf_counter() - start) * 1000
            local_addr = sock.getsockname()
            remote_addr = sock.getpeername()
            log(f"  TCP connection SUCCESS in {elapsed_ms:.1f}ms")
            log(f"  Local endpoint:  {local_addr[0]}:{local_addr[1]}")
            log(f"  Remote endpoint: {remote_addr[0]}:{remote_addr[1]}")
            return True
    except OSError as exc:
        elapsed_ms = (time.perf_counter() - start) * 1000
        log(f"  TCP connection FAILED after {elapsed_ms:.1f}ms: {exc}")
        log(f"  errno: {exc.errno}")
        return False


def test_escpos_connection(host: str, port: int, timeout: float, profile: str | None) -> bool:
    """Test python-escpos Network printer connection."""
    log("Importing python-escpos ...")
    try:
        import escpos
        log(f"  python-escpos version: {escpos.__version__}")
    except ImportError:
        log("  FAILED: python-escpos is not installed.")
        log("  Install with: pip install python-escpos")
        return False
    except AttributeError:
        log("  python-escpos imported (version attribute not available)")

    try:
        from escpos.printer import Network
        log("  escpos.printer.Network imported OK")
    except ImportError as exc:
        log(f"  FAILED to import escpos.printer.Network: {exc}")
        return False

    # Show available profiles if requested
    if profile:
        log(f"Using printer profile: '{profile}'")
        try:
            from escpos.capabilities import get_profile
            p = get_profile(profile)
            log(f"  Profile found: {p.profile_data.get('name', profile)}")
            log(f"  Columns (normal): {p.get_columns('default')}")
        except Exception as exc:
            log(f"  WARNING: Could not load profile '{profile}': {exc}")
            log("  Falling back to default profile")
            profile = None

    # List some available profiles for reference
    try:
        from escpos.capabilities import get_profile, PROFILES  # noqa: F811
        log(f"  Total available profiles: {len(PROFILES)}")
        epson_profiles = [name for name in sorted(PROFILES) if "epson" in name.lower() or "tm-" in name.lower() or "TM-" in name]
        if epson_profiles:
            log(f"  Epson-related profiles: {', '.join(epson_profiles[:15])}")
    except Exception:
        pass

    log(f"Creating Network printer object (host={host}, port={port}, timeout={timeout}) ...")
    try:
        kwargs: dict = {
            "host": host,
            "port": port,
            "timeout": timeout,
        }
        if profile:
            kwargs["profile"] = profile

        printer = Network(**kwargs)
        log("  Network printer object created OK")
    except Exception as exc:
        log(f"  FAILED to create printer object: {exc}")
        traceback.print_exc()
        return False

    # Print device info
    log("Printer object details:")
    for attr in ["host", "port", "timeout", "profile"]:
        val = getattr(printer, attr, "N/A")
        if hasattr(val, "profile_data"):
            log(f"  {attr}: {val.profile_data.get('name', val)}")
        else:
            log(f"  {attr}: {val}")

    # Attempt to open the device
    log("Opening printer connection ...")
    try:
        printer.open()
        log("  printer.open() succeeded")
    except Exception as exc:
        log(f"  printer.open() FAILED: {exc}")
        traceback.print_exc()
        return False

    # Check if device is writable
    log("Checking device state ...")
    try:
        if hasattr(printer, "device") and printer.device is not None:
            log(f"  Device object: {type(printer.device).__name__}")
        else:
            log("  Device object: None (may be normal for Network)")
    except Exception as exc:
        log(f"  Could not inspect device: {exc}")

    # Try printing
    log("Sending test print ...")
    try:
        printer.set(align="center")
        log("  Set alignment to center")

        printer.text("================================\n")
        printer.text("    ESC/POS Connection Test\n")
        printer.text("================================\n")
        printer.text("\n")
        printer.text(f"Host: {host}:{port}\n")
        if profile:
            printer.text(f"Profile: {profile}\n")
        printer.text(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        printer.text("\n")

        printer.set(align="left")
        printer.text("Hello, World!\n")
        printer.text("\n")
        printer.text("If you can read this, your\n")
        printer.text("printer connection is working.\n")
        printer.text("\n")
        log("  Text sent OK")
    except Exception as exc:
        log(f"  FAILED sending text: {exc}")
        traceback.print_exc()
        _close_printer(printer)
        return False

    # Try cut
    log("Sending cut command ...")
    try:
        printer.cut()
        log("  Cut command sent OK")
    except Exception as exc:
        log(f"  Cut command failed (non-fatal): {exc}")

    # Close
    _close_printer(printer)
    log("Test print completed successfully!")
    return True


def _close_printer(printer: object) -> None:
    log("Closing printer connection ...")
    try:
        if hasattr(printer, "close"):
            printer.close()  # type: ignore[union-attr]
        log("  Connection closed OK")
    except Exception as exc:
        log(f"  Close failed (non-fatal): {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test network ESC/POS thermal printer connectivity and printing."
    )
    parser.add_argument("host", help="Printer IP address or hostname")
    parser.add_argument("--port", type=int, default=9100, help="Printer port (default: 9100)")
    parser.add_argument("--profile", default=None, help="Printer profile name (e.g. TM-T20II)")
    parser.add_argument("--timeout", type=float, default=5.0, help="Connection timeout in seconds (default: 5)")
    args = parser.parse_args()

    print("=" * 50)
    print("  ESC/POS Network Printer Diagnostic Test")
    print("=" * 50)
    print()
    log(f"Target: {args.host}:{args.port}")
    log(f"Profile: {args.profile or '(default)'}")
    log(f"Timeout: {args.timeout}s")
    print()

    # Step 1: DNS
    print("--- Step 1: DNS Resolution ---")
    resolved_ip = test_dns_resolution(args.host)
    if resolved_ip is None:
        log("ABORT: Cannot resolve hostname.")
        return 1
    print()

    # Step 2: TCP
    print("--- Step 2: TCP Connectivity ---")
    tcp_ok = test_tcp_connection(args.host, args.port, args.timeout)
    if not tcp_ok:
        log("ABORT: TCP connection failed.")
        log("Troubleshooting tips:")
        log("  - Verify the printer is powered on")
        log("  - Check the IP address is correct")
        log("  - Ensure port 9100 is not blocked by a firewall")
        log("  - Try pinging the printer: ping " + args.host)
        log("  - Check the printer's network config printout")
        return 1
    print()

    # Step 3: ESC/POS
    print("--- Step 3: ESC/POS Print Test ---")
    escpos_ok = test_escpos_connection(args.host, args.port, args.timeout, args.profile)
    if not escpos_ok:
        log("ESC/POS test FAILED.")
        log("Troubleshooting tips:")
        log("  - The TCP connection worked, so the printer IS reachable")
        log("  - Try a different profile (--profile)")
        log("  - Check python-escpos is installed: pip show python-escpos")
        log("  - Some printers need a different port (try 9100, 9200, 515)")
        return 1
    print()

    print("=" * 50)
    log("ALL TESTS PASSED")
    print("=" * 50)
    return 0


if __name__ == "__main__":
    sys.exit(main())
