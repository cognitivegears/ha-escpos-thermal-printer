"""Basic functionality integration tests for ESCPOS printer."""

import pytest

from tests.integration_tests.fixtures import MockDataGenerator, VerificationUtilities

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_print_text_service(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test basic text printing functionality."""
    printer, ha_env, config = printer_with_ha

    # Generate test data
    test_text = MockDataGenerator.generate_text_content(50)

    # Call the print_text service
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {
            'text': test_text,
            'align': 'center',
            'bold': True
        },
        blocking=True
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify the printer received the command
    print_history = await printer.get_print_history()
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('text', print_history, command_log)
    assert VerificationUtilities.verify_print_content(test_text, print_history)


@pytest.mark.asyncio
async def test_print_qr_service(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test QR code printing functionality."""
    printer, ha_env, config = printer_with_ha

    # Generate test QR data
    qr_data = MockDataGenerator.generate_qr_data()

    # Call the print_qr service
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_qr',
        {
            'data': qr_data,
            'size': 6,
            'align': 'center'
        },
        blocking=True
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify the printer received the QR command
    print_history = await printer.get_print_history()
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('qr', print_history, command_log)


@pytest.mark.asyncio
async def test_print_barcode_service(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test barcode printing functionality."""
    printer, ha_env, config = printer_with_ha

    # Generate test barcode data
    barcode_data = MockDataGenerator.generate_barcode_data('CODE128')

    # Call the print_barcode service
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_barcode',
        {
            'code': barcode_data,
            'bc': 'CODE128',
            'height': 64,
            'width': 3
        },
        blocking=True
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify the printer received the barcode command
    print_history = await printer.get_print_history()
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('barcode', print_history, command_log)


@pytest.mark.asyncio
async def test_feed_and_cut_services(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test feed and cut functionality."""
    printer, ha_env, config = printer_with_ha

    # Test feed service
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'feed',
        {'lines': 3},
        blocking=True
    )

    # Test cut service
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'cut',
        {'mode': 'full'},
        blocking=True
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify the printer received both commands
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('feed', [], command_log)
    assert VerificationUtilities.verify_printer_received('cut', [], command_log)


@pytest.mark.asyncio
async def test_multiple_services_sequence(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test a sequence of multiple print services."""
    printer, ha_env, config = printer_with_ha

    # Execute a sequence of services
    services_sequence = [
        ('print_text', {'text': 'Header', 'align': 'center', 'bold': True}),
        ('feed', {'lines': 1}),
        ('print_qr', {'data': 'https://example.com', 'size': 4}),
        ('feed', {'lines': 1}),
        ('print_text', {'text': 'Footer', 'align': 'center'}),
        ('cut', {'mode': 'partial'})
    ]

    for service, data in services_sequence:
        await ha_env.hass.services.async_call(
            'escpos_printer',
            service,
            data,
            blocking=True
        )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify the command sequence
    command_log = await printer.get_command_log()
    expected_sequence = ['text', 'feed', 'qr', 'feed', 'text', 'cut']

    assert VerificationUtilities.verify_command_sequence(expected_sequence, command_log)


@pytest.mark.asyncio
async def test_service_parameter_variations(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test various parameter combinations for services."""
    printer, ha_env, config = printer_with_ha

    # Clear any commands from fixture setup
    await printer.printer_state.clear_history()

    # Test different text formatting options
    formatting_options = [
        {'bold': True, 'underline': 'single', 'align': 'left'},
        {'bold': False, 'underline': 'double', 'align': 'center'},
        {'bold': True, 'underline': 'none', 'align': 'right'},
        {'width': 'double', 'height': 'double', 'align': 'center'}
    ]

    for i, options in enumerate(formatting_options):
        test_text = f"Test formatting {i + 1}"
        data = {'text': test_text}
        data.update(options)

        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            data,
            blocking=True
        )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify all text commands were processed
    command_log = await printer.get_command_log()
    text_commands = [cmd for cmd in command_log if cmd.command_type == 'text']

    assert len(text_commands) == len(formatting_options)


@pytest.mark.asyncio
async def test_printer_state_tracking(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test that printer state is properly tracked."""
    printer, ha_env, config = printer_with_ha

    # Get initial state
    initial_state = await printer.get_status()

    # Perform some operations
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'State tracking test'},
        blocking=True
    )

    await ha_env.hass.services.async_call(
        'escpos_printer',
        'feed',
        {'lines': 2},
        blocking=True
    )

    await ha_env.async_block_till_done()

    # Get final state
    final_state = await printer.get_status()

    # Verify state changes
    assert final_state['command_log_count'] > initial_state['command_log_count']
    assert final_state['online'] == initial_state['online']  # Should remain online
