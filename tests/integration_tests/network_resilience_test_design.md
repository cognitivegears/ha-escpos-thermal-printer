# Network Resilience Testing Design (`test_network_resilience.py`)

## File Structure Overview

```mermaid
flowchart TD
    A[test_network_resilience.py] --> B[Fixtures]
    A --> C[Connection Drop Tests]
    A --> D[Latency Tests]
    A --> E[Packet Tests]
    A --> F[Network Barrier Tests]
    A --> G[Name Resolution Tests]

    B --> B1[network_simulator_fixture]
    B --> B2[reconnecting_printer_fixture]
    B --> B3[unstable_network_fixture]
    B --> B4[packet_control_fixture]

    C --> C1[test_connection_loss_during_print]
    C --> C2[test_reconnection_logic]
    C --> C3[test_multiple_disconnects]
    C --> C4[test_partial_transmission]

    D --> D1[test_high_latency_printing]
    D --> D2[test_variable_latency]
    D --> D3[test_latency_spikes]
    D --> D4[test_timeout_recovery]

    E --> E1[test_packet_fragmentation]
    E --> E2[test_packet_loss]
    E --> E3[test_packet_corruption]
    E --> E4[test_out_of_order_packets]

    F --> F1[test_firewall_interaction]
    F --> F2[test_proxy_handling]
    F --> F3[test_port_filtering]
    F --> F4[test_connection_limiting]

    G --> G1[test_dns_resolution_failures]
    G --> G2[test_ip_vs_hostname]
    G --> G3[test_ipv4_ipv6_compatibility]
    G --> G4[test_hostname_caching]
```

## Fixtures Design

### `network_simulator_fixture` Fixture

This fixture provides network condition simulation capabilities for testing.

```python
@pytest.fixture
async def network_simulator():
    """Fixture providing network condition simulation capabilities."""
    class NetworkSimulator:
        def __init__(self):
            self.active_conditions = []

        async def set_condition(self, condition_type, **params):
            """Set a network condition."""
            condition = {
                'type': condition_type,
                'params': params,
                'active': True
            }
            self.active_conditions.append(condition)
            return condition

        async def clear_condition(self, condition):
            """Clear a specific network condition."""
            if condition in self.active_conditions:
                condition['active'] = False
                self.active_conditions.remove(condition)

        async def clear_all_conditions(self):
            """Clear all network conditions."""
            self.active_conditions = []

        async def simulate_disconnect(self, duration=None):
            """Simulate a network disconnect for a specified duration (seconds)."""
            condition = await self.set_condition('disconnect', duration=duration)

            if duration:
                await asyncio.sleep(duration)
                await self.clear_condition(condition)

            return condition

        async def simulate_latency(self, latency_ms, jitter_ms=0, duration=None):
            """Simulate network latency with optional jitter."""
            condition = await self.set_condition('latency',
                                               latency_ms=latency_ms,
                                               jitter_ms=jitter_ms)

            if duration:
                await asyncio.sleep(duration)
                await self.clear_condition(condition)

            return condition

        async def simulate_packet_loss(self, loss_percentage, duration=None):
            """Simulate packet loss at the specified percentage."""
            condition = await self.set_condition('packet_loss',
                                               percentage=loss_percentage)

            if duration:
                await asyncio.sleep(duration)
                await self.clear_condition(condition)

            return condition

        async def simulate_packet_corruption(self, corruption_percentage, duration=None):
            """Simulate packet corruption at the specified percentage."""
            condition = await self.set_condition('packet_corruption',
                                               percentage=corruption_percentage)

            if duration:
                await asyncio.sleep(duration)
                await self.clear_condition(condition)

            return condition

    return NetworkSimulator()
```

### `reconnecting_printer_fixture` Fixture

This fixture provides a printer that can be configured to disconnect and reconnect during testing.

```python
@pytest.fixture
async def reconnecting_printer(network_simulator):
    """Fixture providing a printer that can be configured to disconnect and reconnect."""
    # Create a printer with network simulation capabilities
    printer = await VirtualPrinter(host='127.0.0.1', port=9100).start()

    # Add network simulation methods to the printer
    printer.network_simulator = network_simulator

    # Add a method to disconnect the printer
    async def disconnect_printer(duration=None):
        """Disconnect the printer for a specified duration."""
        await printer.simulate_error('offline')

        if duration:
            await asyncio.sleep(duration)
            await printer.reset()

    # Add the method to the printer
    printer.disconnect = disconnect_printer

    # Add a method to simulate connection instability
    async def simulate_unstable_connection(disconnect_count=3,
                                          disconnect_duration=1.0,
                                          online_duration=2.0,
                                          total_duration=None):
        """Simulate an unstable connection with multiple disconnects/reconnects."""
        start_time = time.time()
        cycle_count = 0

        while (total_duration is None or time.time() - start_time < total_duration) and \
              (disconnect_count is None or cycle_count < disconnect_count):

            # Disconnect the printer
            await printer.simulate_error('offline')
            await asyncio.sleep(disconnect_duration)

            # Reconnect the printer
            await printer.reset()
            await asyncio.sleep(online_duration)

            cycle_count += 1

    # Add the method to the printer
    printer.simulate_unstable_connection = simulate_unstable_connection

    try:
        yield printer
    finally:
        await printer.stop()
```

### `unstable_network_fixture` Fixture

This fixture sets up an environment with network instability for testing resilience.

```python
@pytest.fixture
async def unstable_network(ha_test_environment, reconnecting_printer, network_simulator):
    """Fixture providing an environment with network instability for testing."""
    # Initialize the Home Assistant environment
    ha_env = ha_test_environment

    # Configure integration with the reconnecting printer
    config = {
        'host': '127.0.0.1',
        'port': 9100,
        'timeout': 5.0,
        'codepage': 'cp437',
        'reconnect_attempts': 3,  # Allow multiple reconnection attempts
        'retry_interval': 1.0     # Wait 1 second between retries
    }

    await ha_env.initialize_integration(config)

    # Create an object to track test state
    test_state = {
        'printer': reconnecting_printer,
        'ha_env': ha_env,
        'network_simulator': network_simulator,
        'config': config,
        'error_count': 0,
        'recovery_count': 0
    }

    # Add a method to count errors
    async def count_error():
        test_state['error_count'] += 1

    # Add a method to count recoveries
    async def count_recovery():
        test_state['recovery_count'] += 1

    # Register error and recovery handlers
    reconnecting_printer.on_error = count_error
    reconnecting_printer.on_recovery = count_recovery

    yield test_state

    # Clean up
    await network_simulator.clear_all_conditions()
```

### `packet_control_fixture` Fixture

This fixture provides fine-grained control over packet handling for network testing.

```python
@pytest.fixture
async def packet_control(network_simulator):
    """Fixture providing fine-grained control over packet handling."""
    class PacketController:
        def __init__(self, network_simulator):
            self.network_simulator = network_simulator
            self.fragmentation_size = None
            self.drop_pattern = None
            self.corruption_bytes = None

        async def set_fragmentation(self, max_packet_size):
            """Set maximum packet size to force fragmentation."""
            self.fragmentation_size = max_packet_size
            await self.network_simulator.set_condition('fragmentation',
                                                     max_size=max_packet_size)

        async def set_drop_pattern(self, pattern):
            """Set a pattern for dropping packets (e.g., "1,5,9" to drop packets 1, 5, and 9)."""
            self.drop_pattern = pattern
            await self.network_simulator.set_condition('drop_pattern', pattern=pattern)

        async def set_corruption_bytes(self, byte_positions):
            """Set specific byte positions to corrupt in packets."""
            self.corruption_bytes = byte_positions
            await self.network_simulator.set_condition('corruption_bytes',
                                                     positions=byte_positions)

        async def reset(self):
            """Reset all packet control settings."""
            self.fragmentation_size = None
            self.drop_pattern = None
            self.corruption_bytes = None
            await self.network_simulator.clear_all_conditions()

    return PacketController(network_simulator)
```

## Test Cases Design

### Connection Drop Tests

```python
@pytest.mark.asyncio
async def test_connection_loss_during_print(unstable_network):
    """Test handling of connection loss during print operations."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']

    # Start a print job
    print_task = asyncio.create_task(
        ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': 'This print job will be interrupted'},
            blocking=True
        )
    )

    # Give the print job time to start
    await asyncio.sleep(0.5)

    # Disconnect the printer mid-print
    await printer.disconnect(duration=2.0)  # Disconnect for 2 seconds

    try:
        # Wait for the print task to complete or fail
        await print_task

        # If we get here, the print task didn't fail - check if it completed
        command_log = await printer.get_command_log()
        text_commands = [cmd for cmd in command_log if cmd.command_type == 'text']
        assert len(text_commands) > 0

    except Exception as e:
        # The print job failed - verify that reconnection attempts were made
        assert "connection" in str(e).lower() or "offline" in str(e).lower()

    # Verify the printer is back online
    status = await printer.get_status()
    assert status['online'] == True

@pytest.mark.asyncio
async def test_reconnection_logic(unstable_network):
    """Test printer reconnection logic after connection loss."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']

    # Disconnect the printer
    await printer.disconnect()

    # Verify the printer is offline
    status = await printer.get_status()
    assert status['online'] == False

    # First print attempt should fail
    with pytest.raises(Exception):
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': 'This should fail'},
            blocking=True
        )

    # Bring the printer back online
    await printer.reset()

    # Wait for reconnection to be detected
    await asyncio.sleep(1)

    # Next print should succeed
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'This should succeed after reconnection'},
        blocking=True
    )

    # Verify the second print command was processed
    command_log = await printer.get_command_log()
    text_commands = [cmd for cmd in command_log
                    if cmd.command_type == 'text' and 'succeed' in str(cmd)]
    assert len(text_commands) > 0

@pytest.mark.asyncio
async def test_multiple_disconnects(unstable_network):
    """Test handling of multiple disconnect/reconnect cycles."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']

    # Set up an unstable connection (3 disconnect/reconnect cycles)
    connection_task = asyncio.create_task(
        printer.simulate_unstable_connection(
            disconnect_count=3,
            disconnect_duration=1.0,
            online_duration=2.0
        )
    )

    # Try to print during this unstable period
    success_count = 0
    failure_count = 0

    for i in range(10):
        try:
            await ha_env.hass.services.async_call(
                'escpos_printer',
                'print_text',
                {'text': f'Unstable connection test {i}'},
                blocking=True
            )
            success_count += 1
        except Exception:
            failure_count += 1

        # Wait a bit before next attempt
        await asyncio.sleep(0.5)

    # Wait for the connection simulation to complete
    await connection_task

    # Verify we had both successes and failures
    assert success_count > 0
    assert failure_count > 0

    # Verify the printer ends up online
    status = await printer.get_status()
    assert status['online'] == True

    # Final print should succeed
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'Final print after stability restored'},
        blocking=True
    )

    # Verify the final print was successful
    command_log = await printer.get_command_log()
    final_prints = [cmd for cmd in command_log
                   if cmd.command_type == 'text' and 'Final print' in str(cmd)]
    assert len(final_prints) == 1
```

### Latency Tests

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("latency_ms", [
    100,    # Moderate latency
    500,    # High latency
    1000,   # Very high latency
])
async def test_high_latency_printing(unstable_network, latency_ms):
    """Test printing under high network latency conditions."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']
    network_simulator = unstable_network['network_simulator']

    # Set up latency condition
    await network_simulator.simulate_latency(latency_ms)

    start_time = time.time()

    # Print with latency
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': f'High latency ({latency_ms}ms) test'},
        blocking=True
    )

    # Measure how long the operation took
    operation_time = time.time() - start_time

    # Clear latency condition
    await network_simulator.clear_all_conditions()

    # Verify the command was processed
    command_log = await printer.get_command_log()
    latency_prints = [cmd for cmd in command_log
                     if cmd.command_type == 'text' and f'({latency_ms}ms)' in str(cmd)]
    assert len(latency_prints) == 1

    # Latency should affect the operation time
    # For example, a 1000ms latency should add at least 1 second to the operation
    # (this is a simplistic check - real network effects would be more complex)
    expected_min_time = latency_ms / 1000  # Convert to seconds
    assert operation_time >= expected_min_time

@pytest.mark.asyncio
async def test_variable_latency(unstable_network):
    """Test printing with variable network latency."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']
    network_simulator = unstable_network['network_simulator']

    # Set up variable latency condition (base latency with jitter)
    await network_simulator.simulate_latency(latency_ms=200, jitter_ms=100)

    # Perform multiple print operations under variable latency
    operation_times = []

    for i in range(5):
        start_time = time.time()

        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': f'Variable latency test {i + 1}'},
            blocking=True
        )

        operation_times.append(time.time() - start_time)

    # Clear latency condition
    await network_simulator.clear_all_conditions()

    # Verify the commands were processed
    command_log = await printer.get_command_log()
    latency_prints = [cmd for cmd in command_log
                     if cmd.command_type == 'text' and 'Variable latency' in str(cmd)]
    assert len(latency_prints) == 5

    # Check for variation in operation times due to jitter
    time_variance = max(operation_times) - min(operation_times)
    assert time_variance > 0  # Should be some variance

@pytest.mark.asyncio
async def test_latency_spikes(unstable_network):
    """Test handling of latency spikes during operation."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']
    network_simulator = unstable_network['network_simulator']

    # Start with normal conditions
    # Then perform a series of prints with different latency conditions

    # Normal latency
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'Normal latency test'},
        blocking=True
    )

    # Introduce a latency spike
    await network_simulator.simulate_latency(latency_ms=1000)

    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'High latency spike test'},
        blocking=True
    )

    # Return to normal latency
    await network_simulator.clear_all_conditions()

    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': 'Normal latency after spike test'},
        blocking=True
    )

    # Verify all commands were processed
    command_log = await printer.get_command_log()
    normal_prints = [cmd for cmd in command_log
                    if cmd.command_type == 'text' and 'Normal latency' in str(cmd)]
    spike_prints = [cmd for cmd in command_log
                   if cmd.command_type == 'text' and 'High latency spike' in str(cmd)]

    assert len(normal_prints) == 2  # Before and after spike
    assert len(spike_prints) == 1  # During spike
```

### Packet Tests

```python
@pytest.mark.asyncio
async def test_packet_fragmentation(unstable_network, packet_control):
    """Test handling of packet fragmentation."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']

    # Set up packet fragmentation (small maximum packet size)
    await packet_control.set_fragmentation(max_packet_size=64)

    # Generate a large text content that will require fragmentation
    large_text = 'X' * 1024  # 1KB of data

    # Print the large content
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': large_text},
        blocking=True
    )

    # Reset packet control
    await packet_control.reset()

    # Verify the large content was printed correctly
    print_history = await printer.get_print_history()

    # Check that the content was received correctly despite fragmentation
    assert VerificationUtilities.verify_print_content(large_text, print_history)

@pytest.mark.asyncio
@pytest.mark.parametrize("loss_percentage", [
    5,    # Minimal packet loss
    20,   # Moderate packet loss
    40    # Severe packet loss
])
async def test_packet_loss(unstable_network, loss_percentage):
    """Test handling of packet loss."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']
    network_simulator = unstable_network['network_simulator']

    # Set up packet loss condition
    await network_simulator.simulate_packet_loss(loss_percentage=loss_percentage)

    # Try to print with packet loss
    test_text = f"Packet loss ({loss_percentage}%) test"

    try:
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': test_text},
            blocking=True
        )

        # If we get here, the print succeeded despite packet loss
        print_success = True
    except Exception:
        # Print failed due to packet loss
        print_success = False

    # Clear packet loss condition
    await network_simulator.clear_all_conditions()

    # For minimal packet loss, print should succeed
    # For severe packet loss, print may fail
    if loss_percentage <= 5:
        assert print_success, "Print should succeed with minimal packet loss"

    # If print succeeded, verify content
    if print_success:
        print_history = await printer.get_print_history()
        command_log = await printer.get_command_log()

        # Verify the text was printed correctly or at least attempted
        assert VerificationUtilities.verify_printer_received('text', print_history, command_log)

@pytest.mark.asyncio
async def test_packet_corruption(unstable_network, packet_control):
    """Test handling of packet corruption."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']
    network_simulator = unstable_network['network_simulator']

    # Set up packet corruption condition
    await network_simulator.simulate_packet_corruption(corruption_percentage=10)

    # Try to print with packet corruption
    test_text = "Packet corruption test"

    try:
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': test_text},
            blocking=True
        )

        print_success = True
    except Exception:
        # Print failed due to corruption
        print_success = False

    # Clear corruption condition
    await network_simulator.clear_all_conditions()

    # Verify the printer state after corruption test
    status = await printer.get_status()
    assert status['online'] == True, "Printer should remain online after corruption test"

    # If print succeeded, try another print to verify printer is still functional
    if print_success:
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': "After corruption test"},
            blocking=True
        )

        # Verify both prints were received
        command_log = await printer.get_command_log()
        text_commands = [cmd for cmd in command_log if cmd.command_type == 'text']
        assert len(text_commands) >= 2
```

### Network Barrier Tests

```python
@pytest.mark.asyncio
async def test_firewall_interaction(unstable_network, network_simulator):
    """Test printing through simulated firewall conditions."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']

    # Simulate a firewall that temporarily blocks connections
    # We'll simulate this by disconnecting the printer for a short time

    # Initial print should succeed
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': "Before firewall block"},
        blocking=True
    )

    # Simulate firewall blocking the connection
    await printer.disconnect(duration=3.0)

    # Try to print while connection is blocked
    with pytest.raises(Exception):
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': "During firewall block - should fail"},
            blocking=True
        )

    # Wait for the connection to be restored
    await asyncio.sleep(3.5)

    # Print after connection is restored
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': "After firewall block - should succeed"},
        blocking=True
    )

    # Verify prints before and after the block succeeded
    command_log = await printer.get_command_log()
    before_prints = [cmd for cmd in command_log
                    if cmd.command_type == 'text' and 'Before firewall' in str(cmd)]
    after_prints = [cmd for cmd in command_log
                   if cmd.command_type == 'text' and 'After firewall' in str(cmd)]

    assert len(before_prints) == 1
    assert len(after_prints) == 1

@pytest.mark.asyncio
async def test_connection_limiting(unstable_network, network_simulator):
    """Test behavior when connections are limited or throttled."""
    printer = unstable_network['printer']
    ha_env = unstable_network['ha_env']

    # Simulate connection limiting by adding high latency and occasional disconnects
    latency_condition = await network_simulator.simulate_latency(latency_ms=300)

    # Start a background task that simulates intermittent connection issues
    async def random_connection_issues():
        for _ in range(3):
            await asyncio.sleep(random.uniform(0.5, 2.0))
            await printer.disconnect(duration=random.uniform(0.2, 0.8))

    connection_task = asyncio.create_task(random_connection_issues())

    # Try to perform multiple print operations during this unstable period
    results = []

    for i in range(10):
        try:
            await ha_env.hass.services.async_call(
                'escpos_printer',
                'print_text',
                {'text': f"Connection limiting test {i+1}"},
                blocking=True
            )
            results.append(True)  # Success
        except Exception:
            results.append(False)  # Failure

        await asyncio.sleep(0.5)

    # Wait for the connection issues to finish
    await connection_task

    # Clear all network conditions
    await network_simulator.clear_all_conditions()

    # Verify some prints succeeded and some failed
    assert True in results, "Some prints should succeed"
    assert False in results, "Some prints should fail due to connection limits"

    # Final print after conditions are cleared should succeed
    await ha_env.hass.services.async_call(
        'escpos_printer',
        'print_text',
        {'text': "After connection limiting test"},
        blocking=True
    )

    # Verify the final print succeeded
    command_log = await printer.get_command_log()
    after_prints = [cmd for cmd in command_log
                   if cmd.command_type == 'text' and 'After connection limiting' in str(cmd)]
    assert len(after_prints) == 1
```

### Name Resolution Tests

```python
@pytest.mark.asyncio
@pytest.mark.parametrize("address_type", ["hostname", "ip_address"])
async def test_ip_vs_hostname(address_type, custom_config_fixture, ha_test_environment):
    """Test using hostname vs IP address for printer connection."""
    ha_env = ha_test_environment

    # Create appropriate config based on address type
    if address_type == "hostname":
        host = "localhost"
    else:
        host = "127.0.0.1"

    config = custom_config_fixture(host=host)

    # Start a printer server on localhost/127.0.0.1
    printer = await VirtualPrinter(host='127.0.0.1', port=9100).start()

    try:
        # Initialize integration with the config
        await ha_env.initialize_integration(config)

        # Try a test print
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': f"Address type test: {address_type}"},
            blocking=True
        )

        await ha_env.async_block_till_done()

        # Verify the print was successful
        command_log = await printer.get_command_log()
        address_prints = [cmd for cmd in command_log
                         if cmd.command_type == 'text' and f'Address type test: {address_type}' in str(cmd)]

        assert len(address_prints) == 1

    finally:
        # Clean up
        await printer.stop()

@pytest.mark.asyncio
async def test_dns_resolution_failures(custom_config_fixture, ha_test_environment):
    """Test handling of DNS resolution failures."""
    ha_env = ha_test_environment

    # Configure with a non-existent hostname
    config = custom_config_fixture(host='nonexistent.local')

    # Initialize integration with the bad config
    try:
        await ha_env.initialize_integration(config)
        initialization_failed = False
    except Exception as e:
        initialization_failed = True
        # Verify the error is related to DNS resolution
        assert "resolve" in str(e).lower() or "host" in str(e).lower()

    # Initialization should fail due to DNS resolution error
    assert initialization_failed, "Initialization should fail with non-existent hostname"

    # Now try with a valid configuration
    valid_config = custom_config_fixture(host='127.0.0.1')

    # Start a printer server
    printer = await VirtualPrinter(host='127.0.0.1', port=9100).start()

    try:
        # Initialize with valid config
        await ha_env.initialize_integration(valid_config)

        # Test print should succeed
        await ha_env.hass.services.async_call(
            'escpos_printer',
            'print_text',
            {'text': "After DNS failure test"},
            blocking=True
        )

        await ha_env.async_block_till_done()

        # Verify the print was successful
        command_log = await printer.get_command_log()
        dns_prints = [cmd for cmd in command_log
                     if cmd.command_type == 'text' and 'After DNS failure' in str(cmd)]

        assert len(dns_prints) == 1

    finally:
        await printer.stop()
```

## Required Enhancements

To fully implement these network resilience tests, we'll need several enhancements to the test framework:

1. **Network Simulation Layer**: Add a network simulation layer to the virtual printer emulator that can introduce various network conditions:
   - Connection drops/disconnects
   - Latency and jitter
   - Packet loss and corruption
   - Packet fragmentation

2. **Connection State Management**: Enhance the printer emulator to track connection state and manage reconnection logic:
   - Connection event hooks
   - Automatic and manual reconnection logic
   - Connection state transitions

3. **Network Condition Controller**: Create a controller for applying and removing network conditions:
   - Apply multiple conditions simultaneously
   - Schedule condition changes
   - Monitor condition effects

4. **Testing Utilities**: Develop utilities to verify system behavior under network stress:
   - Connection attempt tracking
   - Recovery verification
   - Performance under degraded conditions

## Implementation Notes

These network resilience tests require significant enhancements to the virtual printer emulator to simulate network conditions. The implementation should focus on:

1. **Realistic Simulation**: Ensure network conditions simulate real-world scenarios accurately
2. **Controllable Behavior**: Make network conditions controllable and reproducible
3. **Observable Effects**: Provide ways to observe and verify system behavior under network stress
4. **Recovery Validation**: Focus on testing recovery mechanisms and fault tolerance

The tests should verify that the ESCPOS integration can:

- Detect and handle network failures gracefully
- Recover when network conditions improve
- Maintain consistent state across network interruptions
- Properly report errors to Home Assistant
- Apply appropriate retry and timeout behaviors
