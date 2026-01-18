"""ESCPOS Printer Integration Test Framework.

This package provides a comprehensive framework for testing the Home Assistant
ESCPOS thermal printer integration with realistic scenarios including:

- Virtual printer emulator that simulates ESCPOS protocol
- Home Assistant test environment for automation testing
- Error simulation and recovery testing
- Performance and concurrency testing
- Comprehensive test utilities and fixtures

The framework enables testing of real integration behavior rather than
just mocked components, ensuring reliable operation in production scenarios.
"""

import importlib
from typing import Any

from .emulator import (
    Command,
    ErrorSimulator,
    EscposCommandParser,
    PrinterState,
    PrintJob,
    VirtualPrinter,
    VirtualPrinterServer,
    create_connection_error,
    create_intermittent_error,
    create_offline_error,
    create_paper_out_error,
    create_timeout_error,
)


# Lazy import HA environment to avoid dependency conflicts
def _import_ha_environment() -> tuple[type[Any], type[Any], type[Any], type[Any]]:
    """Import HA environment modules on demand."""
    try:
        from .ha_environment import (
            AutomationTester,
            HATestEnvironment,
            NotificationTester,
            StateChangeSimulator,
        )
        return HATestEnvironment, StateChangeSimulator, AutomationTester, NotificationTester
    except ImportError as e:
        raise ImportError(
            f"Failed to import HA environment: {e}. "
            "This may be due to Home Assistant dependency conflicts. "
            "Try installing without 'pytest-homeassistant-custom-component' "
            "or use only the virtual printer emulator."
        ) from e

from .fixtures import MockDataGenerator, VerificationUtilities


# Provide access to HA environment without importing on module load
def get_ha_environment() -> Any:
    """Get HA environment classes, importing them only when needed."""
    return _import_ha_environment()

__version__ = "1.0.0"

__all__ = [
    'Command',
    'ErrorSimulator',
    'EscposCommandParser',
    'MockDataGenerator',
    'PrintJob',
    'PrinterState',
    # Test Utilities
    'VerificationUtilities',
    'VirtualPrinter',
    # Virtual Printer Emulator
    'VirtualPrinterServer',
    # Home Assistant Environment (lazy loaded)
    '_import_ha_environment',  # Function to import HA components when needed
    'create_connection_error',
    'create_intermittent_error',
    'create_offline_error',
    'create_paper_out_error',
    'create_timeout_error',
    'get_ha_environment'      # Convenience function for HA components
]
