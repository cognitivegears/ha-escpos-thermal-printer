"""Automation integration tests for ESCPOS printer."""

import pytest

from tests.integration_tests.fixtures import MockDataGenerator, VerificationUtilities


@pytest.mark.asyncio
async def test_state_triggered_print_automation(printer_with_ha, automation_config) -> None:  # type: ignore[no-untyped-def]
    """Test automation that prints when a state changes."""
    printer, ha_env, _config = printer_with_ha

    # Load the automation
    automation_id = await ha_env.automation_tester.load_automation(automation_config)

    # Create and set up the trigger entity
    await ha_env.create_test_entity('sensor.test_sensor', 'sensor', 'off')

    # Trigger the automation by changing the entity state
    await ha_env.state_simulator.trigger_state_change(
        'sensor.test_sensor',
        'off',
        'on'
    )

    # Wait for automation processing
    await ha_env.async_block_till_done()

    # Verify automation ran
    assert await ha_env.automation_tester.verify_automation_ran(automation_id)

    # Verify print service was called
    service_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls) > 0

    # Verify printer received the command
    print_history = await printer.get_print_history()
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('text', print_history, command_log)


@pytest.mark.asyncio
async def test_multiple_state_triggers(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test automation with multiple state triggers."""
    _printer, ha_env, _config = printer_with_ha

    # Create automation with multiple triggers
    multi_trigger_config = {
        'id': 'multi_trigger_test',
        'alias': 'Multi Trigger Test',
        'trigger': [
            {
                'platform': 'state',
                'entity_id': 'sensor.trigger1',
                'to': 'active'
            },
            {
                'platform': 'state',
                'entity_id': 'sensor.trigger2',
                'to': 'active'
            }
        ],
        'action': {
            'service': 'escpos_printer.print_text',
            'data': {
                'text': 'Multi-trigger activation!',
                'align': 'center'
            }
        }
    }

    await ha_env.automation_tester.load_automation(multi_trigger_config)

    # Create trigger entities
    await ha_env.create_test_entity('sensor.trigger1', 'sensor', 'inactive')
    await ha_env.create_test_entity('sensor.trigger2', 'sensor', 'inactive')

    # Trigger first entity
    await ha_env.state_simulator.trigger_state_change(
        'sensor.trigger1',
        'inactive',
        'active'
    )

    await ha_env.async_block_till_done()

    # Check first trigger
    service_calls_after_first = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls_after_first) == 1

    # Trigger second entity
    await ha_env.state_simulator.trigger_state_change(
        'sensor.trigger2',
        'inactive',
        'active'
    )

    await ha_env.async_block_till_done()

    # Check second trigger
    service_calls_after_second = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls_after_second) == 2


@pytest.mark.asyncio
async def test_conditional_print_automation(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test automation with conditions for printing."""
    _printer, ha_env, _config = printer_with_ha

    # Create automation with conditions
    conditional_config = {
        'id': 'conditional_print_test',
        'alias': 'Conditional Print Test',
        'trigger': {
            'platform': 'state',
            'entity_id': 'sensor.main_trigger',
            'to': 'activate'
        },
        'condition': {
            'condition': 'and',
            'conditions': [
                {
                    'condition': 'state',
                    'entity_id': 'sensor.condition1',
                    'state': 'enabled'
                },
                {
                    'condition': 'state',
                    'entity_id': 'sensor.condition2',
                    'state': 'ready'
                }
            ]
        },
        'action': {
            'service': 'escpos_printer.print_text',
            'data': {
                'text': 'Conditions met - printing!',
                'bold': True
            }
        }
    }

    await ha_env.automation_tester.load_automation(conditional_config)

    # Create entities
    await ha_env.create_test_entity('sensor.main_trigger', 'sensor', 'idle')
    await ha_env.create_test_entity('sensor.condition1', 'sensor', 'disabled')
    await ha_env.create_test_entity('sensor.condition2', 'sensor', 'not_ready')

    # Trigger without conditions met (should not print)
    await ha_env.state_simulator.trigger_state_change(
        'sensor.main_trigger',
        'idle',
        'activate'
    )

    await ha_env.async_block_till_done()

    # Check no print occurred
    service_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls) == 0

    # Set conditions
    await ha_env.state_simulator.set_state('sensor.condition1', 'enabled')
    await ha_env.state_simulator.set_state('sensor.condition2', 'ready')

    # Reset trigger and activate again
    await ha_env.state_simulator.set_state('sensor.main_trigger', 'idle')
    await ha_env.state_simulator.trigger_state_change(
        'sensor.main_trigger',
        'idle',
        'activate'
    )

    await ha_env.async_block_till_done()

    # Check print occurred
    service_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls) == 1


@pytest.mark.asyncio
async def test_notification_triggered_print(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test printing triggered by notifications."""
    printer, ha_env, _config = printer_with_ha

    # Send a notification
    test_message = MockDataGenerator.generate_text_content(30)
    await ha_env.notification_tester.send_notification(
        message=test_message,
        title="Test Notification"
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify notification was sent
    assert await ha_env.notification_tester.verify_notification_sent()

    # Verify print action occurred
    assert await ha_env.notification_tester.verify_print_action()

    # Verify printer received the content
    print_history = await printer.get_print_history()
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('text', print_history, command_log)
    assert VerificationUtilities.verify_print_content(test_message, print_history)


@pytest.mark.asyncio
async def test_automation_sequence_with_multiple_services(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test automation that calls multiple printer services in sequence."""
    printer, ha_env, _config = printer_with_ha

    # Clear command history from fixture initialization
    await printer.printer_state.clear_history()

    # Create automation with multiple service calls
    sequence_config = {
        'id': 'sequence_test',
        'alias': 'Service Sequence Test',
        'trigger': {
            'platform': 'state',
            'entity_id': 'sensor.sequence_trigger',
            'to': 'start'
        },
        'action': [
            {
                'service': 'escpos_printer.print_text',
                'data': {
                    'text': 'Header',
                    'align': 'center',
                    'bold': True
                }
            },
            {
                'service': 'escpos_printer.feed',
                'data': {'lines': 1}
            },
            {
                'service': 'escpos_printer.print_qr',
                'data': {
                    'data': MockDataGenerator.generate_qr_data(),
                    'size': 4
                }
            },
            {
                'service': 'escpos_printer.feed',
                'data': {'lines': 1}
            },
            {
                'service': 'escpos_printer.print_text',
                'data': {
                    'text': 'Footer',
                    'align': 'center'
                }
            },
            {
                'service': 'escpos_printer.cut',
                'data': {'mode': 'full'}
            }
        ]
    }

    await ha_env.automation_tester.load_automation(sequence_config)

    # Create trigger entity
    await ha_env.create_test_entity('sensor.sequence_trigger', 'sensor', 'idle')

    # Trigger the automation
    await ha_env.state_simulator.trigger_state_change(
        'sensor.sequence_trigger',
        'idle',
        'start'
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify all services were called
    text_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
    qr_calls = ha_env.get_service_calls('escpos_printer', 'print_qr')
    feed_calls = ha_env.get_service_calls('escpos_printer', 'feed')
    cut_calls = ha_env.get_service_calls('escpos_printer', 'cut')

    assert len(text_calls) == 2  # Header and footer
    assert len(qr_calls) == 1
    assert len(feed_calls) == 2
    assert len(cut_calls) == 1

    # Verify command sequence on printer
    command_log = await printer.get_command_log()
    expected_sequence = ['text', 'feed', 'qr', 'feed', 'text', 'cut']

    assert VerificationUtilities.verify_command_sequence(expected_sequence, command_log)


@pytest.mark.asyncio
async def test_automation_with_template_data(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test automation that uses template data for printing."""
    printer, ha_env, _config = printer_with_ha

    # Create automation with template
    template_config = {
        'id': 'template_test',
        'alias': 'Template Test',
        'trigger': {
            'platform': 'state',
            'entity_id': 'sensor.temperature',
            'to': 'changed'
        },
        'action': {
            'service': 'escpos_printer.print_text',
            'data': {
                'text': "Temperature: {{ states('sensor.temperature') }}°C at {{ now().strftime('%H:%M') }}",
                'align': 'center'
            }
        }
    }

    await ha_env.automation_tester.load_automation(template_config)

    # Create temperature sensor
    await ha_env.create_test_entity('sensor.temperature', 'sensor', '20')

    # Trigger automation
    await ha_env.state_simulator.trigger_state_change(
        'sensor.temperature',
        '20',
        '25'
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify service was called
    service_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
    assert len(service_calls) == 1

    # Verify printer received command
    print_history = await printer.get_print_history()
    command_log = await printer.get_command_log()

    assert VerificationUtilities.verify_printer_received('text', print_history, command_log)


@pytest.mark.asyncio
async def test_automation_error_handling(printer_with_ha) -> None:  # type: ignore[no-untyped-def]
    """Test automation behavior when printer errors occur."""
    printer, ha_env, _config = printer_with_ha

    # Create automation
    error_test_config = {
        'id': 'error_test',
        'alias': 'Error Handling Test',
        'trigger': {
            'platform': 'state',
            'entity_id': 'sensor.error_trigger',
            'to': 'trigger'
        },
        'action': {
            'service': 'escpos_printer.print_text',
            'data': {
                'text': 'This should handle errors gracefully',
                'align': 'center'
            }
        }
    }

    automation_id = await ha_env.automation_tester.load_automation(error_test_config)

    # Create trigger entity
    await ha_env.create_test_entity('sensor.error_trigger', 'sensor', 'idle')

    # Simulate printer error
    await printer.simulate_error('offline')

    # Trigger automation
    await ha_env.state_simulator.trigger_state_change(
        'sensor.error_trigger',
        'idle',
        'trigger'
    )

    # Wait for processing
    await ha_env.async_block_till_done()

    # Verify automation attempted to run (even if print failed)
    assert await ha_env.automation_tester.verify_automation_ran(automation_id)

    # Verify error was recorded
    error_history = await printer.error_simulator.get_error_history()
    assert len(error_history) > 0
