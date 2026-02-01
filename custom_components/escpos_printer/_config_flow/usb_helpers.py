"""USB discovery and connectivity helper functions for config flow."""

from __future__ import annotations

import logging
from typing import Any

from ..const import DEFAULT_IN_EP, DEFAULT_OUT_EP, THERMAL_PRINTER_VIDS

_LOGGER = logging.getLogger(__name__)


def _parse_vid_pid(value: int | str) -> int:
    """Parse a VID or PID value from various formats.

    Handles:
    - Integer values: returned as-is
    - "0x04b8" or "0X04B8": parsed as hex with prefix
    - "04b8": parsed as hex (contains hex letters a-f)
    - "1208": parsed as decimal (pure digits)

    Args:
        value: The VID/PID value as int or string

    Returns:
        The parsed integer value

    Raises:
        ValueError: If the value cannot be parsed
    """
    if isinstance(value, int):
        return value

    if not isinstance(value, str):
        raise TypeError(f"Expected int or str, got {type(value).__name__}")

    value = value.strip()
    if not value:
        raise ValueError("Empty string")

    # Check for 0x/0X prefix - parse as hex
    if value.lower().startswith("0x"):
        return int(value, 16)

    # Check if string contains hex letters (a-f) - parse as hex
    if any(c in value.lower() for c in "abcdef"):
        return int(value, 16)

    # Pure digits - parse as decimal
    return int(value, 10)


def _can_connect_usb(  # noqa: PLR0911, PLR0912
    vendor_id: int,
    product_id: int,
    timeout: float,
    in_ep: int = DEFAULT_IN_EP,
    out_ep: int = DEFAULT_OUT_EP,
) -> tuple[bool, str | None, int | None]:
    """Test USB connectivity to a device.

    Args:
        vendor_id: USB Vendor ID
        product_id: USB Product ID
        timeout: Connection timeout in seconds
        in_ep: USB input endpoint address
        out_ep: USB output endpoint address

    Returns:
        Tuple of (success, error_message, errno). error_message and errno are None on success.
    """
    def _get_errno(exc: Exception) -> int | None:
        return getattr(exc, "errno", None)

    def _get_kernel_driver_active() -> bool | None:
        try:
            import usb.core  # noqa: PLC0415

            device = usb.core.find(idVendor=vendor_id, idProduct=product_id)
            if device is None or not hasattr(device, "is_kernel_driver_active"):
                return None
            try:
                return bool(device.is_kernel_driver_active(0))
            except Exception:
                return None
        except Exception:
            return None

    def _is_retryable(exc: Exception) -> bool:
        try:
            import usb.core  # noqa: PLC0415

            if isinstance(exc, usb.core.USBError):
                return exc.errno in {5, 16, 19}  # EIO, EBUSY, ENODEV
        except Exception:
            _LOGGER.debug(
                "Could not use usb.core to determine if USB error is retryable; "
                "falling back to string-based heuristic.",
                exc_info=True,
            )
        err = str(exc).lower()
        return any(token in err for token in ("input/output error", "resource busy", "no device"))

    try:
        from escpos.printer import Usb  # noqa: PLC0415

        for attempt in range(3):
            try:
                printer = Usb(
                    vendor_id,
                    product_id,
                    timeout=int(timeout * 1000),
                    in_ep=in_ep,
                    out_ep=out_ep,
                )
                printer.close()
                break
            except Exception as exc:
                if attempt >= 2 or not _is_retryable(exc):
                    raise
                import time  # noqa: PLC0415

                time.sleep(0.3)
    except PermissionError:
        return False, "permission_denied", None
    except FileNotFoundError:
        return False, "device_not_found", None
    except Exception as ex:
        errno = _get_errno(ex)
        kernel_driver_active = _get_kernel_driver_active()
        # Check for libusb permission errors (varies by platform)
        error_str = str(ex).lower()
        if errno == 13 or "access" in error_str or "permission" in error_str:
            return False, "permission_denied", errno
        if errno == 16:
            if kernel_driver_active:
                return False, "kernel_driver_active", errno
            return False, "device_busy", errno
        if errno == 19 or "not found" in error_str:
            return False, "device_not_found", errno
        if "no backend" in error_str:
            return False, "usb_backend_missing", errno
        if errno == 5 or "input/output error" in error_str:
            return False, "io_error", errno
        _LOGGER.debug(
            "USB connection test failed (errno=%s kernel_driver_active=%s): %s",
            errno,
            kernel_driver_active,
            ex,
        )
        return False, None, errno
    else:
        return True, None, None


def _generate_usb_unique_id(
    vendor_id: int, product_id: int, serial_number: str | None = None
) -> str:
    """Generate a unique ID for a USB device.

    Uses serial number when available to distinguish identical printers.

    Args:
        vendor_id: USB Vendor ID
        product_id: USB Product ID
        serial_number: Device serial number (optional)

    Returns:
        Unique ID string
    """
    base_id = f"usb:{vendor_id:04x}:{product_id:04x}"
    if serial_number:
        # Include serial for uniqueness when multiple identical printers exist
        return f"{base_id}:{serial_number}"
    return base_id


def _usb_error_to_key(error_code: str | None) -> str:
    """Convert USB error code to form error key.

    Args:
        error_code: Error code from _can_connect_usb

    Returns:
        Error key for strings.json
    """
    error_map = {
        "permission_denied": "usb_permission_denied",
        "kernel_driver_active": "usb_kernel_driver_active",
        "device_busy": "usb_device_busy",
        "io_error": "usb_io_error",
        "device_not_found": "usb_device_not_found",
        "usb_backend_missing": "usb_backend_missing",
    }
    return error_map.get(error_code or "", "cannot_connect_usb")


def _discover_usb_printers() -> list[dict[str, Any]]:
    """Discover connected USB thermal printers.

    Returns:
        List of dictionaries containing printer information
    """
    try:
        import usb.core  # noqa: PLC0415
        import usb.util  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning("pyusb not installed, USB printer discovery unavailable")
        return []

    printers: list[dict[str, Any]] = []
    try:
        for device in usb.core.find(find_all=True):
            if device.idVendor in THERMAL_PRINTER_VIDS:
                try:
                    manufacturer = usb.util.get_string(device, device.iManufacturer) or "Unknown"
                    product = usb.util.get_string(device, device.iProduct) or "Thermal Printer"
                    # Try to get serial number for unique identification
                    serial = None
                    try:
                        if device.iSerialNumber:
                            serial = usb.util.get_string(device, device.iSerialNumber)
                    except Exception:
                        # Serial number access may fail due to permissions or device quirks;
                        # it's optional and used only to distinguish identical printers
                        pass
                    printers.append({
                        "vendor_id": device.idVendor,
                        "product_id": device.idProduct,
                        "manufacturer": manufacturer,
                        "product": product,
                        "serial_number": serial,
                        "label": f"{manufacturer} {product} ({device.idVendor:04X}:{device.idProduct:04X})",
                    })
                except Exception:
                    printers.append({
                        "vendor_id": device.idVendor,
                        "product_id": device.idProduct,
                        "manufacturer": "Unknown",
                        "product": "Thermal Printer",
                        "serial_number": None,
                        "label": f"Thermal Printer ({device.idVendor:04X}:{device.idProduct:04X})",
                    })
    except Exception as e:
        _LOGGER.debug("USB device enumeration failed: %s", e)

    return printers


def _discover_all_usb_devices() -> list[dict[str, Any]]:
    """Discover all connected USB devices (not filtered by vendor).

    Returns:
        List of dictionaries containing device information
    """
    try:
        import usb.core  # noqa: PLC0415
        import usb.util  # noqa: PLC0415
    except ImportError:
        _LOGGER.warning("pyusb not installed, USB device discovery unavailable")
        return []

    devices: list[dict[str, Any]] = []
    try:
        for device in usb.core.find(find_all=True):
            try:
                manufacturer = usb.util.get_string(device, device.iManufacturer) or "Unknown"
                product = usb.util.get_string(device, device.iProduct) or "USB Device"
                # Try to get serial number for unique identification
                serial = None
                try:
                    if device.iSerialNumber:
                        serial = usb.util.get_string(device, device.iSerialNumber)
                except Exception:
                    # Serial number access may fail due to permissions or device quirks;
                    # it's optional and used only to distinguish identical devices
                    pass
                # Note if this is a known thermal printer vendor
                is_known_printer = device.idVendor in THERMAL_PRINTER_VIDS
                devices.append({
                    "vendor_id": device.idVendor,
                    "product_id": device.idProduct,
                    "manufacturer": manufacturer,
                    "product": product,
                    "serial_number": serial,
                    "is_known_printer": is_known_printer,
                    "label": f"{manufacturer} {product} ({device.idVendor:04X}:{device.idProduct:04X})",
                })
            except Exception:
                devices.append({
                    "vendor_id": device.idVendor,
                    "product_id": device.idProduct,
                    "manufacturer": "Unknown",
                    "product": "USB Device",
                    "serial_number": None,
                    "is_known_printer": device.idVendor in THERMAL_PRINTER_VIDS,
                    "label": f"USB Device ({device.idVendor:04X}:{device.idProduct:04X})",
                })
    except Exception as e:
        _LOGGER.debug("USB device enumeration failed: %s", e)

    return devices


def _build_usb_device_choices(
    printers: list[dict[str, Any]], include_browse_all: bool = True
) -> dict[str, str]:
    """Build device choice dictionary from discovered printers.

    Generates unique keys for each printer to handle multiple devices with
    the same VID/PID. Uses serial number when available, otherwise adds an
    index suffix.

    Args:
        printers: List of discovered printer dictionaries
        include_browse_all: Whether to include "Browse all USB devices..." option

    Returns:
        Dictionary mapping choice keys to display labels
    """
    device_choices: dict[str, str] = {}
    vid_pid_counts: dict[str, int] = {}  # Track devices without serial by VID:PID

    for printer in printers:
        vid_pid = f"{printer['vendor_id']:04X}:{printer['product_id']:04X}"
        serial = printer.get("serial_number")

        if serial:
            # Use serial number to distinguish devices
            key = f"{vid_pid}:{serial}"
        else:
            # Use index suffix for devices without serial that share VID:PID
            count = vid_pid_counts.get(vid_pid, 0)
            vid_pid_counts[vid_pid] = count + 1
            # Include count suffix to make each device selectable
            key = f"{vid_pid}#{count}"

        # Store the key in the printer dict for later lookup
        printer["_choice_key"] = key
        device_choices[key] = printer["label"]

    # Add browse all devices option
    if include_browse_all:
        device_choices["__browse_all__"] = "Browse all USB devices..."

    # Add manual entry option
    device_choices["__manual__"] = "Manual entry (VID:PID)..."

    return device_choices
