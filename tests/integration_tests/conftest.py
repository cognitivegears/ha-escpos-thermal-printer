"""Shared integration-test configuration and fixtures.

Explicitly imports fixtures from tests/integration_tests/fixtures/conftest.py
to make them available to tests in sibling packages like scenarios/.
This file marks tests as 'integration' and conditionally enables sockets.
"""

from typing import Any

import pytest

# Import fixtures to make them available to test scenarios
from tests.integration_tests.fixtures.conftest import (
    automation_config,
    error_printer_server,
    ha_test_environment,
    mock_printer_server,
    printer_with_ha,
    sample_print_data,
    temp_image_file,
    test_config,
    virtual_printer,
)


@pytest.fixture(autouse=True)
def _enable_sockets_for_integration(request: Any) -> None:
    """Enable sockets only for integration tests.

    Uses the 'socket_enabled' fixture provided by pytest-socket which is
    included via pytest-homeassistant-custom-component.
    """
    node = request.node
    if node.get_closest_marker("integration") or "tests/integration_tests/" in str(getattr(node, "fspath", "")):
        # Will raise if fixture is absent; in our env it should exist
        request.getfixturevalue("socket_enabled")


def pytest_collection_modifyitems(config: Any, items: Any) -> None:
    """Mark all tests under tests/integration_tests as integration."""
    for item in items:
        if "tests/integration_tests/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
