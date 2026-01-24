"""Factory function for creating printer adapters."""

from __future__ import annotations

from .base_adapter import EscposPrinterAdapterBase
from .config import PrinterConfigTypes, UsbPrinterConfig
from .network_adapter import NetworkPrinterAdapter
from .usb_adapter import UsbPrinterAdapter


def create_printer_adapter(config: PrinterConfigTypes) -> EscposPrinterAdapterBase:
    """Factory function to create the appropriate printer adapter based on configuration."""
    if isinstance(config, UsbPrinterConfig):
        return UsbPrinterAdapter(config)
    return NetworkPrinterAdapter(config)
