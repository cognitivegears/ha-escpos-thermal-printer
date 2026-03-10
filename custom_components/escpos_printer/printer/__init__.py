"""Printer adapter package for ESC/POS thermal printers.

This package provides adapters for communicating with ESC/POS thermal printers
over network (TCP/IP), USB, and CUPS connections.
"""

from __future__ import annotations

from .base_adapter import EscposPrinterAdapterBase
from .config import (
    BasePrinterConfig,
    CupsPrinterConfig,
    NetworkPrinterConfig,
    PrinterConfig,
    PrinterConfigTypes,
    UsbPrinterConfig,
)
from .cups_adapter import CupsPrinterAdapter
from .factory import create_printer_adapter
from .network_adapter import NetworkPrinterAdapter
from .usb_adapter import UsbPrinterAdapter

# Legacy alias for backward compatibility
EscposPrinterAdapter = NetworkPrinterAdapter

__all__ = [
    "BasePrinterConfig",
    "CupsPrinterAdapter",
    "CupsPrinterConfig",
    "EscposPrinterAdapter",
    "EscposPrinterAdapterBase",
    "NetworkPrinterAdapter",
    "NetworkPrinterConfig",
    "PrinterConfig",
    "PrinterConfigTypes",
    "UsbPrinterAdapter",
    "UsbPrinterConfig",
    "create_printer_adapter",
]
