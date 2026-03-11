"""Factory function for creating printer adapters."""

from __future__ import annotations

from .base_adapter import EscposPrinterAdapterBase
from .config import CupsPrinterConfig, PrinterConfigTypes, UsbPrinterConfig
from .cups_adapter import CupsPrinterAdapter
from .network_adapter import NetworkPrinterAdapter
from .usb_adapter import UsbPrinterAdapter


def create_printer_adapter(config: PrinterConfigTypes) -> EscposPrinterAdapterBase:
    """Factory function to create the appropriate printer adapter based on configuration."""
    if isinstance(config, UsbPrinterConfig):
        return UsbPrinterAdapter(config)
    if isinstance(config, CupsPrinterConfig):
        return CupsPrinterAdapter(config)
    return NetworkPrinterAdapter(config)
