# ESCPOS Printer Integration Test Framework

A comprehensive framework for testing the Home Assistant ESCPOS thermal printer integration with realistic scenarios, virtual printer emulation, and Home Assistant automation testing.

## Overview

This framework enables thorough testing of the ESCPOS printer integration by providing:

- **Virtual Printer Emulator**: TCP server that simulates ESCPOS protocol behavior
- **Home Assistant Test Environment**: Realistic HA simulation with state changes and automations
- **Error Simulation**: Programmable error conditions and recovery testing
- **Comprehensive Test Scenarios**: Basic functionality, error handling, automations, and performance
- **Test Utilities**: Verification tools, mock data generators, and reusable fixtures

## Quick Start

### Basic Test Example

```python
import pytest
from tests.integration_tests.fixtures import VerificationUtilities, MockDataGenerator

@pytest.mark.asyncio
async def test_print_text_service(printer_with_ha):
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
```

### Running Tests

```bash
# Run all integration tests
pytest tests/integration_tests/

# Run specific test scenarios
pytest tests/integration_tests/scenarios/test_basic_functionality.py
pytest tests/integration_tests/scenarios/test_error_handling.py
pytest tests/integration_tests/scenarios/test_automation_integration.py

# Run with verbose output
pytest tests/integration_tests/ -v

# Run with coverage
pytest tests/integration_tests/ --cov=custom_components.escpos_printer --cov-report=html
```

## Architecture

### Core Components

#### 1. Virtual Printer Emulator (`emulator/`)

The virtual printer emulator provides a complete ESCPOS-compatible TCP server:

```python
from tests.integration_tests.emulator import VirtualPrinter

async def test_with_virtual_printer():
    async with VirtualPrinter(host='127.0.0.1', port=9100) as printer:
        # Printer is now running and accepting connections
        status = await printer.get_status()
        print(f"Printer status: {status}")

        # Simulate errors
        await printer.simulate_error('offline')

        # Get command history
        commands = await printer.get_command_log()
        prints = await printer.get_print_history()
```

**Key Features:**

- ESCPOS command parsing (text, QR, barcode, images, etc.)
- Printer state management (online/offline, paper status)
- Error simulation (offline, timeout, paper out, etc.)
- Command history and print job tracking

#### 2. Home Assistant Test Environment (`ha_environment/`)

Provides a realistic Home Assistant testing environment:

```python
from tests.integration_tests.ha_environment import HATestEnvironment

@pytest.mark.asyncio
async def test_with_ha_environment(hass):
    env = HATestEnvironment(hass)
    await env.setup()

    try:
        # Initialize the integration
        config = {'host': '127.0.0.1', 'port': 9100, 'timeout': 5.0}
        await env.initialize_integration(config)

        # Test state changes
        await env.state_simulator.set_state('sensor.test', 'on')

        # Test automations
        automation_config = {
            'id': 'test_auto',
            'trigger': {'platform': 'state', 'entity_id': 'sensor.test'},
            'action': {'service': 'escpos_printer.print_text', 'data': {'text': 'Hello'}}
        }
        await env.automation_tester.load_automation(automation_config)

        # Test notifications
        await env.notification_tester.send_notification("Test message")

    finally:
        await env.teardown()
```

**Key Features:**

- Isolated HA instance setup
- State change simulation
- Automation testing framework
- Notification integration testing
- Service call tracking

#### 3. Test Fixtures (`fixtures/`)

Reusable pytest fixtures and utilities:

```python
@pytest.mark.asyncio
async def test_with_fixtures(printer_with_ha, temp_image_file):
    """Test using pre-configured fixtures."""
    printer, ha_env, config = printer_with_ha

    # Print an image using temporary file fixture
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_image',
        {'image': temp_image_file, 'align': 'center'},
        blocking=True
    )

    await ha_env.async_block_till_done()

    # Verify image command was received
    command_log = await printer.get_command_log()
    assert VerificationUtilities.verify_printer_received('image', [], command_log)
```

**Available Fixtures:**

- `virtual_printer`: Standalone virtual printer server
- `ha_test_environment`: HA test environment
- `printer_with_ha`: Combined printer and HA environment
- `temp_image_file`: Temporary image file for testing
- `sample_print_data`: Realistic print job data
- `automation_config`: Sample automation configuration

#### 4. Verification Utilities (`fixtures/verification_utils.py`)

Comprehensive verification tools:

```python
from tests.integration_tests.fixtures import VerificationUtilities

# Verify specific commands were received
assert VerificationUtilities.verify_printer_received('text', print_history, command_log)

# Verify content was printed
assert VerificationUtilities.verify_print_content("Hello World", print_history)

# Verify command sequence
expected_sequence = ['text', 'feed', 'cut']
assert VerificationUtilities.verify_command_sequence(expected_sequence, command_log)

# Verify service calls
service_calls = ha_env.get_service_calls('escpos_printer', 'print_text')
assert VerificationUtilities.verify_service_call(service_calls, 'escpos_printer', 'print_text')
```

#### 5. Mock Data Generator (`fixtures/mock_data_generator.py`)

Generate realistic test data:

```python
from tests.integration_tests.fixtures import MockDataGenerator

# Generate text content
text = MockDataGenerator.generate_text_content(100)

# Generate QR codes
qr_data = MockDataGenerator.generate_qr_data()

# Generate barcodes
barcode = MockDataGenerator.generate_barcode_data('CODE128')

# Generate test images
image = MockDataGenerator.generate_test_image(200, 100, "receipt")

# Generate automation configs
automation = MockDataGenerator.generate_automation_config("state")
```

## Test Scenarios

### Basic Functionality Tests

Located in `scenarios/test_basic_functionality.py`:

- **Service Call Tests**: All printer services (print_text, print_qr, print_image, etc.)
- **Parameter Variations**: Different alignments, styles, encodings
- **Service Sequences**: Multiple services in sequence
- **State Tracking**: Verify printer state changes

### Error Handling Tests

Located in `scenarios/test_error_handling.py`:

- **Connection Errors**: Offline, timeout, connection refused
- **Protocol Errors**: Malformed commands, buffer overflows
- **Recovery Tests**: Reconnection, error state clearing
- **Programmable Errors**: Custom error conditions and triggers

### Automation Integration Tests

Located in `scenarios/test_automation_integration.py`:

- **State Triggers**: Entity state changes triggering prints
- **Conditional Printing**: Conditions based on multiple entities
- **Template Data**: Dynamic content using HA templates
- **Notification Integration**: Notifications triggering prints
- **Error Handling**: Automation behavior during printer errors

## Error Simulation

The framework provides comprehensive error simulation capabilities:

### Predefined Error Conditions

```python
from tests.integration_tests.emulator import (
    create_offline_error,
    create_paper_out_error,
    create_timeout_error,
    create_connection_error,
    create_intermittent_error
)

# Create error conditions
offline_error = create_offline_error(trigger_type='after_commands', trigger_value=5)
paper_error = create_paper_out_error(trigger_type='random', trigger_value=0.1)

# Add to printer
await printer.error_simulator.add_error_condition(offline_error)
await printer.error_simulator.add_error_condition(paper_error)
```

### Manual Error Control

```python
# Trigger errors manually
await printer.simulate_error('offline')
await printer.simulate_error('paper_out')

# Check error history
error_history = await printer.error_simulator.get_error_history()

# Reset error simulator
await printer.error_simulator.reset()
```

## Configuration

### Virtual Printer Configuration

```yaml
virtual_printer:
  host: '127.0.0.1'
  port: 9100
  buffer_size: 4096
  connection_timeout: 5.0
  error_simulation:
    enabled: false
    error_type: null  # offline, timeout, paper_out, etc.
    trigger_after: 0  # commands or seconds
```

### Home Assistant Test Environment

```yaml
ha_environment:
  config_dir: './test_config'
  automations:
    - id: 'test_print_on_state'
      trigger:
        platform: 'state'
        entity_id: 'sensor.test_sensor'
      action:
        service: 'escpos_printer.print_text'
        data:
          text: 'State changed!'

  entities:
    - entity_id: 'sensor.test_sensor'
      state: 'initial'
      attributes:
        friendly_name: 'Test Sensor'
```

## Advanced Usage

### Custom Test Scenarios

```python
import pytest
from tests.integration_tests import (
    VirtualPrinter,
    HATestEnvironment,
    VerificationUtilities,
    MockDataGenerator
)

@pytest.mark.asyncio
async def test_custom_scenario(hass):
    """Custom test scenario example."""
    # Start virtual printer
    async with VirtualPrinter(port=9101) as printer:
        # Set up HA environment
        env = HATestEnvironment(hass)
        await env.setup()

        try:
            # Initialize integration
            config = {'host': '127.0.0.1', 'port': 9101, 'timeout': 5.0}
            await env.initialize_integration(config)

            # Create custom automation
            custom_auto = {
                'id': 'custom_test',
                'trigger': {'platform': 'event', 'event_type': 'test_event'},
                'action': {
                    'service': 'escpos_printer.print_text',
                    'data': {'text': 'Custom automation triggered!'}
                }
            }

            await env.automation_tester.load_automation(custom_auto)

            # Trigger the automation
            await env.automation_tester.trigger_automation('custom_test', {})

            # Verify results
            print_history = await printer.get_print_history()
            assert VerificationUtilities.verify_print_content(
                'Custom automation triggered!', print_history
            )

        finally:
            await env.teardown()
```

### Performance Testing

```python
@pytest.mark.asyncio
async def test_concurrent_operations(printer_with_ha):
    """Test concurrent print operations."""
    printer, ha_env, config = printer_with_ha

    # Generate multiple print jobs
    print_jobs = [
        MockDataGenerator.generate_print_job_data('text') for _ in range(10)
    ]

    # Execute concurrently
    tasks = []
    for job in print_jobs:
        task = ha_env.hass.services.async_call(
            'escpos_printer',
            job['type'],
            job['data'],
            blocking=True
        )
        tasks.append(task)

    # Wait for all to complete
    await asyncio.gather(*tasks)
    await ha_env.async_block_till_done()

    # Verify all jobs were processed
    print_history = await printer.get_print_history()
    assert len(print_history) == len(print_jobs)
```

## Best Practices

### Test Organization

1. **Use Descriptive Test Names**: Clearly indicate what each test verifies
2. **Group Related Tests**: Use test classes or modules for related functionality
3. **Clean Up Resources**: Always use try/finally blocks or pytest fixtures for cleanup
4. **Verify State Changes**: Check both service calls and printer state changes

### Error Testing

1. **Test Realistic Scenarios**: Use error conditions that occur in production
2. **Verify Error Handling**: Ensure the integration handles errors gracefully
3. **Test Recovery**: Verify the system can recover from error conditions
4. **Check Logging**: Verify appropriate error messages are logged

### Performance Considerations

1. **Use Appropriate Timeouts**: Set realistic timeouts for operations
2. **Test Concurrent Access**: Verify behavior under concurrent operations
3. **Monitor Resource Usage**: Check for memory leaks or resource exhaustion
4. **Profile Slow Tests**: Identify and optimize performance bottlenecks

## Troubleshooting

### Common Issues

1. **Connection Refused**: Ensure virtual printer is started before HA integration
2. **Timeout Errors**: Check network configuration and timeout settings
3. **Encoding Issues**: Verify text encoding matches printer expectations
4. **State Not Updated**: Ensure `async_block_till_done()` is called after service calls

### Debugging Tips

1. **Enable Debug Logging**:

   ```python
   import logging
   logging.getLogger('tests.integration_tests').setLevel(logging.DEBUG)
   ```

2. **Inspect Command History**:

   ```python
   commands = await printer.get_command_log()
   for cmd in commands:
       print(f"Command: {cmd.command_type}, Data: {cmd.raw_data.hex()}")
   ```

3. **Check Service Calls**:

   ```python
   service_calls = ha_env.get_service_calls()
   for call in service_calls:
       print(f"Service: {call['domain']}.{call['service']}, Data: {call['data']}")
   ```

## Contributing

When adding new test scenarios:

1. Follow the existing naming conventions
2. Add appropriate docstrings and comments
3. Include both positive and negative test cases
4. Update this README with new examples
5. Ensure tests are isolated and don't interfere with each other

## License

This integration test framework is part of the ESCPOS Printer Home Assistant integration and follows the same license terms.
