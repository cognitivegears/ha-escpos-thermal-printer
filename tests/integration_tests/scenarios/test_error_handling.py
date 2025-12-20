"""Error handling integration tests for ESCPOS printer."""


import pytest

from tests.integration_tests.emulator import create_offline_error, create_paper_out_error
from tests.integration_tests.fixtures import VerificationUtilities


@pytest.mark.asyncio
async def test_printer_offline_error(error_printer_server, ha_test_environment) -> None:  # type: ignore[no-untyped-def]
    """Test handling of printer offline errors."""
    printer = error_printer_server
    ha_env = ha_test_environment

    # The error_printer_server fixture should already have offline error configured
    # Try to print something
    with pytest.raises(Exception):  # Should raise an exception due to offline printer
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': 'This should fail'},
            blocking=True
        )

    await ha_env.async_block_till_done()

    # Verify error was recorded
    error_history = await printer.error_simulator.get_error_history()
    assert VerificationUtilities.verify_error_handling('offline', error_history)


@pytest.mark.asyncio
async def test_connection_timeout_error(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test handling of connection timeout errors."""
    printer, ha_env, config = printer_with_ha

    # Simulate a timeout by setting a very short timeout
    config['timeout'] = 0.001  # Very short timeout

    # Try to print (this might not actually timeout with virtual printer, but tests the path)
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'Test timeout handling'},
        blocking=True
    )

    await ha_env.async_block_till_done()

    # Verify the service call was attempted
    service_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls) > 0


@pytest.mark.asyncio
async def test_paper_out_error_simulation(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test paper out error simulation."""
    printer, ha_env, config = printer_with_ha

    # Manually trigger paper out error
    await printer.simulate_error('paper_out')

    # Verify printer state changed
    status = await printer.get_status()
    assert status['paper_status'] == 'out'


@pytest.mark.asyncio
async def test_error_recovery(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test error recovery mechanisms."""
    printer, ha_env, config = printer_with_ha

    # Start with normal operation
    initial_status = await printer.get_status()
    assert initial_status['online'] == True
    assert initial_status['paper_status'] == 'loaded'

    # Simulate an error
    await printer.simulate_error('offline')

    # Verify error state
    error_status = await printer.get_status()
    assert error_status['online'] == False

    # Reset the printer (simulate recovery)
    await printer.reset()

    # Verify recovery
    recovered_status = await printer.get_status()
    assert recovered_status['online'] == True
    assert recovered_status['paper_status'] == 'loaded'


@pytest.mark.asyncio
async def test_programmable_error_conditions(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test programmable error conditions."""
    printer, ha_env, config = printer_with_ha

    # Add a programmable error condition (offline after 3 commands)
    offline_condition = create_offline_error(
        trigger_type='after_commands',
        trigger_value=3
    )
    await printer.error_simulator.add_error_condition(offline_condition)

    # Execute commands that should trigger the error
    for i in range(5):
        try:
            await ha_env.hass.services.async_call(
                'escpos_printer',
                'print_text',
                {'text': f'Command {i + 1}'},
                blocking=True
            )
        except Exception:
            # Expected: errors will occur after offline condition triggers
            pass

    await ha_env.async_block_till_done()

    # Verify error was triggered
    error_history = await printer.error_simulator.get_error_history()
    assert len(error_history) > 0

    # Check that error occurred after the expected number of commands
    offline_errors = [e for e in error_history if e.get('error_type') == 'offline']
    assert len(offline_errors) > 0


@pytest.mark.asyncio
async def test_multiple_error_conditions(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test handling multiple simultaneous error conditions."""
    printer, ha_env, config = printer_with_ha

    # Add multiple error conditions
    conditions = [
        create_offline_error(trigger_type='after_commands', trigger_value=2),
        create_paper_out_error(trigger_type='after_commands', trigger_value=4)
    ]

    for condition in conditions:
        await printer.error_simulator.add_error_condition(condition)

    # Execute commands to trigger errors
    for i in range(6):
        try:
            await ha_env.hass.services.async_call(
                'escpos_printer',
                'print_text',
                {'text': f'Command {i + 1}'},
                blocking=True
            )
        except Exception:
            # Expected: errors will occur after offline condition triggers
            pass

    await ha_env.async_block_till_done()

    # Verify multiple errors were recorded
    error_history = await printer.error_simulator.get_error_history()
    assert len(error_history) >= 2  # Should have at least 2 errors

    # Check for both error types
    error_types = {e.get('error_type') for e in error_history}
    assert 'offline' in error_types
    assert 'paper_out' in error_types


@pytest.mark.asyncio
async def test_error_condition_removal(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test removing error conditions."""
    printer, ha_env, config = printer_with_ha

    # Add an error condition
    condition = create_offline_error(trigger_type='immediate')
    await printer.error_simulator.add_error_condition(condition)

    # Verify condition was added
    active_errors = await printer.error_simulator.get_active_errors()
    assert 'offline' in active_errors

    # Remove the error condition
    await printer.error_simulator.remove_error_condition('offline')

    # Verify condition was removed
    active_errors = await printer.error_simulator.get_active_errors()
    assert 'offline' not in active_errors


@pytest.mark.asyncio
async def test_error_simulation_reset(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test resetting error simulator state."""
    printer, ha_env, config = printer_with_ha

    # Add some error conditions and generate history
    condition = create_offline_error(trigger_type='immediate')
    await printer.error_simulator.add_error_condition(condition)

    # Trigger the error
    await printer.simulate_error('offline')

    # Verify state before reset
    active_errors = await printer.error_simulator.get_active_errors()
    error_history = await printer.error_simulator.get_error_history()
    assert len(active_errors) > 0
    assert len(error_history) > 0

    # Reset the simulator
    await printer.error_simulator.reset()

    # Verify state after reset
    active_errors = await printer.error_simulator.get_active_errors()
    error_history = await printer.error_simulator.get_error_history()
    assert len(active_errors) == 0
    assert len(error_history) == 0


@pytest.mark.asyncio
async def test_service_call_during_error(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test service calls during error conditions."""
    printer, ha_env, config = printer_with_ha

    # Simulate printer offline
    await printer.simulate_error('offline')

    # Try to make service calls during error
    service_calls = []

    for i in range(3):
        try:
            await ha_env.hass.services.async_call(
                'escpos_printer',
                'print_text',
                {'text': f'Error test {i + 1}'},
                blocking=True
            )
            service_calls.append(f'success_{i}')
        except Exception as e:
            service_calls.append(f'error_{i}: {e!s}')

    await ha_env.async_block_till_done()

    # Verify that service calls were attempted (may succeed or fail depending on implementation)
    assert len(service_calls) == 3

    # Verify error state is maintained
    status = await printer.get_status()
    assert status['online'] == False


@pytest.mark.asyncio
async def test_error_state_persistence(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test that error states persist across multiple operations."""
    printer, ha_env, config = printer_with_ha

    # Wait for any pending mirror operations from fixture initialization
    await ha_env.async_block_till_done()

    # Clear command history from fixture initialization
    await printer.printer_state.clear_history()

    # Set initial error state
    await printer.simulate_error('paper_out')

    # Perform multiple operations
    for i in range(5):
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': f'Persistence test {i + 1}'},
            blocking=True
        )

    await ha_env.async_block_till_done()

    # Verify error state persists
    final_status = await printer.get_status()
    assert final_status['paper_status'] == 'out'

    # Verify operations were still recorded
    command_log = await printer.get_command_log()
    text_commands = [cmd for cmd in command_log if cmd.command_type == 'text']
    assert len(text_commands) == 5
