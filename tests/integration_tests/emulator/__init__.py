"""Virtual printer emulator package for ESCPOS integration testing."""

from .command_parser import EscposCommandParser
from .error_simulator import (
    ErrorCondition,
    ErrorSimulator,
    create_connection_error,
    create_intermittent_error,
    create_offline_error,
    create_paper_out_error,
    create_timeout_error,
)
from .printer_state import Command, PrinterState, PrintJob
from .virtual_printer import VirtualPrinter, VirtualPrinterServer

__all__ = [
    'Command',
    'ErrorCondition',
    'ErrorSimulator',
    'EscposCommandParser',
    'PrintJob',
    'PrinterState',
    'VirtualPrinter',
    'VirtualPrinterServer',
    'create_connection_error',
    'create_intermittent_error',
    'create_offline_error',
    'create_paper_out_error',
    'create_timeout_error'
]

# Global hook to expose the most recently started virtual printer server
# so other test utilities can discover it when fixtures are used separately.
ACTIVE_PRINTER_SERVER: VirtualPrinterServer | None = None

def set_active_server(server: VirtualPrinterServer | None) -> None:
    global ACTIVE_PRINTER_SERVER
    ACTIVE_PRINTER_SERVER = server

def get_active_server() -> VirtualPrinterServer | None:
    return ACTIVE_PRINTER_SERVER
