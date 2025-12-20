"""Verification utilities for ESCPOS integration testing."""

from __future__ import annotations

import logging
from typing import Any

from tests.integration_tests.emulator import Command, PrintJob

_LOGGER = logging.getLogger(__name__)


class VerificationUtilities:
    """Utilities for verifying test results and printer behavior."""

    @staticmethod
    def verify_printer_received(command_type: str, print_history: list[PrintJob],
                               command_log: list[Command]) -> bool:
        """Verify that the printer received a specific type of command."""
        # Check command log for the command type
        matching_commands = [cmd for cmd in command_log if cmd.command_type == command_type]

        if not matching_commands:
            _LOGGER.warning("Command type '%s' not found in command log", command_type)
            return False

        _LOGGER.debug("Found %d commands of type '%s'", len(matching_commands), command_type)
        return True

    @staticmethod
    def verify_print_content(expected_content: str, print_history: list[PrintJob]) -> bool:
        """Verify that specific content was printed."""
        for job in print_history:
            if job.content_type == "text":
                # Check if the expected content is in the printed data
                data_str = job.data.decode('utf-8', errors='ignore') if isinstance(job.data, bytes) else str(job.data)
                if expected_content in data_str:
                    _LOGGER.debug("Found expected content '%s' in print job", expected_content)
                    return True

        _LOGGER.warning("Expected content '%s' not found in print history", expected_content)
        return False

    @staticmethod
    def compare_print_history(expected_jobs: list[dict[str, Any]], actual_jobs: list[PrintJob]) -> bool:
        """Compare expected print jobs with actual print history."""
        if len(expected_jobs) != len(actual_jobs):
            _LOGGER.warning("Print history length mismatch: expected %d, got %d",
                           len(expected_jobs), len(actual_jobs))
            return False

        for i, (expected, actual) in enumerate(zip(expected_jobs, actual_jobs)):
            if not VerificationUtilities._compare_print_job(expected, actual):
                _LOGGER.warning("Print job %d mismatch", i)
                return False

        _LOGGER.debug("Print history comparison successful")
        return True

    @staticmethod
    def _compare_print_job(expected: dict[str, Any], actual: PrintJob) -> bool:
        """Compare a single expected print job with an actual print job."""
        # Check content type
        if expected.get('content_type') != actual.content_type:
            return False

        # Check parameters
        expected_params = expected.get('parameters', {})
        for key, value in expected_params.items():
            if key not in actual.parameters or actual.parameters[key] != value:
                return False

        # For text content, check if expected text is contained
        if actual.content_type == "text" and 'text' in expected:
            data_str = actual.data.decode('utf-8', errors='ignore') if isinstance(actual.data, bytes) else str(actual.data)
            if expected['text'] not in data_str:
                return False

        return True

    @staticmethod
    def verify_command_sequence(expected_sequence: list[str], command_log: list[Command]) -> bool:
        """Verify that commands were executed in the expected sequence."""
        actual_sequence = [cmd.command_type for cmd in command_log]

        # Check if the expected sequence is a subsequence of the actual sequence
        expected_index = 0
        for cmd_type in actual_sequence:
            if cmd_type == expected_sequence[expected_index]:
                expected_index += 1
                if expected_index >= len(expected_sequence):
                    _LOGGER.debug("Command sequence verification successful")
                    return True

        _LOGGER.warning("Command sequence verification failed. Expected: %s, Got: %s",
                       expected_sequence, actual_sequence)
        return False

    @staticmethod
    def verify_service_call(hass_services: list[dict[str, Any]], domain: str,
                           service: str, expected_data: dict[str, Any] | None = None) -> bool:
        """Verify that a specific service was called."""
        matching_calls = [
            call for call in hass_services
            if call['domain'] == domain and call['service'] == service
        ]

        if not matching_calls:
            _LOGGER.warning("Service call %s.%s not found", domain, service)
            return False

        if expected_data:
            # Check if any call matches the expected data
            for call in matching_calls:
                if VerificationUtilities._compare_service_data(expected_data, call['data']):
                    _LOGGER.debug("Service call %s.%s verified with expected data", domain, service)
                    return True
            _LOGGER.warning("Service call %s.%s found but data doesn't match expected", domain, service)
            return False

        _LOGGER.debug("Service call %s.%s verified", domain, service)
        return True

    @staticmethod
    def _compare_service_data(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
        """Compare expected service call data with actual data."""
        for key, value in expected.items():
            if key not in actual or actual[key] != value:
                return False
        return True

    @staticmethod
    def verify_printer_state(expected_state: dict[str, Any], actual_state: dict[str, Any]) -> bool:
        """Verify printer state matches expected values."""
        for key, expected_value in expected_state.items():
            if key not in actual_state:
                _LOGGER.warning("Expected state key '%s' not found in actual state", key)
                return False

            if actual_state[key] != expected_value:
                _LOGGER.warning("State mismatch for '%s': expected %s, got %s",
                               key, expected_value, actual_state[key])
                return False

        _LOGGER.debug("Printer state verification successful")
        return True

    @staticmethod
    def verify_error_handling(error_type: str, error_history: list[dict[str, Any]]) -> bool:
        """Verify that specific error handling occurred."""
        for error_record in error_history:
            if error_record.get('error_type') == error_type:
                _LOGGER.debug("Error handling verified for type: %s", error_type)
                return True

        _LOGGER.warning("Error handling not found for type: %s", error_type)
        return False

    @staticmethod
    def get_print_summary(print_history: list[PrintJob]) -> dict[str, Any]:
        """Get a summary of print activity."""
        content_types: dict[str, int] = {}
        summary: dict[str, Any] = {
            'total_jobs': len(print_history),
            'content_types': content_types,
            'total_commands': 0
        }

        for job in print_history:
            content_type = job.content_type
            content_types[content_type] = content_types.get(content_type, 0) + 1

        return summary

    @staticmethod
    def get_command_summary(command_log: list[Command]) -> dict[str, Any]:
        """Get a summary of command activity."""
        command_types: dict[str, int] = {}
        summary: dict[str, Any] = {
            'total_commands': len(command_log),
            'command_types': command_types
        }

        for cmd in command_log:
            cmd_type = cmd.command_type
            command_types[cmd_type] = command_types.get(cmd_type, 0) + 1

        return summary
