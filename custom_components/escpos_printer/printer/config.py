"""Configuration dataclasses for printer adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from ..const import DEFAULT_IN_EP, DEFAULT_OUT_EP


@dataclass
class BasePrinterConfig:
    """Base printer configuration shared by all connection types."""

    codepage: str | None = None
    profile: str | None = None
    line_width: int = 48
    timeout: float = 4.0


@dataclass
class NetworkPrinterConfig(BasePrinterConfig):
    """Configuration for network (TCP/IP) printers."""

    connection_type: Literal["network"] = field(default="network", repr=False)
    host: str = ""
    port: int = 9100


@dataclass
class UsbPrinterConfig(BasePrinterConfig):
    """Configuration for USB printers."""

    connection_type: Literal["usb"] = field(default="usb", repr=False)
    vendor_id: int = 0
    product_id: int = 0
    in_ep: int = DEFAULT_IN_EP
    out_ep: int = DEFAULT_OUT_EP


# Type alias for config union (use for type hints)
PrinterConfigTypes = NetworkPrinterConfig | UsbPrinterConfig

# Backward-compatible alias: PrinterConfig(...) still works and creates NetworkPrinterConfig
# This maintains API compatibility for existing code that instantiates PrinterConfig directly
PrinterConfig = NetworkPrinterConfig
