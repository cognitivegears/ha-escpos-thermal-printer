#!/usr/bin/env python3
"""
Basic usage example for the ESCPOS Printer Integration Test Framework.

This example demonstrates how to use the framework to test basic printer functionality
with a virtual printer emulator and Home Assistant test environment.
"""

import asyncio
import logging

from tests.integration_tests import (
    MockDataGenerator,
    VerificationUtilities,
    VirtualPrinter,
)

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def basic_printer_test() -> None:
    """Demonstrate basic printer functionality testing."""
    logger.info("Starting basic printer functionality test...")

    # Start virtual printer
    async with VirtualPrinter(host='127.0.0.1', port=9100) as printer:
        logger.info("Virtual printer started on port 9100")

        # Simulate some printer operations
        logger.info("Testing printer operations...")

        # Get initial status
        status = await printer.get_status()
        logger.info(f"Initial printer status: {status}")

        # Simulate receiving some ESCPOS commands
        # In a real test, these would come from the HA integration
        sample_commands = [
            b'\x1b@',  # Initialize printer
            b'Hello World\n',  # Text data
            b'\x1bd\x01',  # Feed 1 line
            b'\x1bi',  # Partial cut
        ]

        # Process commands (this would normally happen automatically)
        for cmd_data in sample_commands:
            # Get command history
            command_log = await printer.get_command_log()
            logger.info(f"Commands processed: {len(command_log)}")

        # Get final status
        final_status = await printer.get_status()
        logger.info(f"Final printer status: {final_status}")

        # Get print history
        print_history = await printer.get_print_history()
        logger.info(f"Print jobs: {len(print_history)}")

        logger.info("Basic printer test completed successfully!")


async def mock_data_generation_example() -> None:
    """Demonstrate mock data generation capabilities."""
    logger.info("Demonstrating mock data generation...")

    # Generate various types of test data
    text_content = MockDataGenerator.generate_text_content(100)
    logger.info(f"Generated text content ({len(text_content)} chars): {text_content[:50]}...")

    qr_data = MockDataGenerator.generate_qr_data()
    logger.info(f"Generated QR data: {qr_data}")

    barcode_data = MockDataGenerator.generate_barcode_data('CODE128')
    logger.info(f"Generated barcode data: {barcode_data}")

    # Generate automation configuration
    automation_config = MockDataGenerator.generate_automation_config('state')
    logger.info(f"Generated automation config: {automation_config['id']}")

    # Generate notification data
    notification = MockDataGenerator.generate_notification_data()
    logger.info(f"Generated notification: {notification['title']}")

    logger.info("Mock data generation demonstration completed!")


async def verification_utilities_example() -> None:
    """Demonstrate verification utilities."""
    logger.info("Demonstrating verification utilities...")

    # Create mock data for testing
    mock_print_history = [
        type('MockPrintJob', (), {
            'content_type': 'text',
            'data': b'Hello World',
            'parameters': {'align': 'center'}
        })()
    ]

    mock_command_log = [
        type('MockCommand', (), {
            'command_type': 'text',
            'raw_data': b'Hello World',
            'parameters': {'text': 'Hello World'}
        })()
    ]

    # Test verification utilities
    text_received = VerificationUtilities.verify_printer_received(
        'text', mock_print_history, mock_command_log
    )
    logger.info(f"Text command received: {text_received}")

    content_found = VerificationUtilities.verify_print_content(
        'Hello World', mock_print_history
    )
    logger.info(f"Content found: {content_found}")

    # Test command sequence verification
    sequence_valid = VerificationUtilities.verify_command_sequence(
        ['text'], mock_command_log
    )
    logger.info(f"Command sequence valid: {sequence_valid}")

    logger.info("Verification utilities demonstration completed!")


async def error_simulation_example() -> None:
    """Demonstrate error simulation capabilities."""
    logger.info("Demonstrating error simulation...")

    async with VirtualPrinter(host='127.0.0.1', port=9101) as printer:
        logger.info("Virtual printer with error simulation started")

        # Get initial status
        initial_status = await printer.get_status()
        logger.info(f"Initial status: online={initial_status['online']}")

        # Simulate printer going offline
        await printer.simulate_error('offline')
        logger.info("Simulated printer offline error")

        # Check status after error
        error_status = await printer.get_status()
        logger.info(f"Status after error: online={error_status['online']}")

        # Check error history
        error_history = await printer.error_simulator.get_error_history()
        logger.info(f"Error history: {len(error_history)} errors recorded")

        # Reset printer
        await printer.reset()
        logger.info("Printer reset")

        # Check status after reset
        reset_status = await printer.get_status()
        logger.info(f"Status after reset: online={reset_status['online']}")

        logger.info("Error simulation demonstration completed!")


async def main() -> None:
    """Run all examples."""
    logger.info("ESCPOS Printer Integration Test Framework - Usage Examples")
    logger.info("=" * 60)

    try:
        # Run examples
        await basic_printer_test()
        logger.info("-" * 40)

        await mock_data_generation_example()
        logger.info("-" * 40)

        await verification_utilities_example()
        logger.info("-" * 40)

        await error_simulation_example()
        logger.info("-" * 40)

        logger.info("All examples completed successfully!")

    except Exception as e:
        logger.error(f"Example failed: {e}")
        raise


if __name__ == "__main__":
    # Run the examples
    asyncio.run(main())
