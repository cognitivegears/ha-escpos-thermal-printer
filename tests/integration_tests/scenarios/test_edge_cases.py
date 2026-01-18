"""Edge cases and boundary testing for ESCPOS printer integration."""

import asyncio

import pytest

from tests.integration_tests.fixtures import MockDataGenerator


class TestEdgeCases:
    """Test edge cases and boundary conditions for the ESCPOS printer integration."""

    @pytest.mark.asyncio
    async def test_very_large_text_content(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test printing very large text content that approaches memory limits."""
        # Generate a very large text content
        large_text = MockDataGenerator.generate_text_content(10000)  # 10KB of text

        # Send the large content to the printer
        printer_state = virtual_printer.printer_state
        await printer_state.update_state_sync('text', large_text.encode('utf-8'), {})

        # Verify the printer handled it correctly
        history = await printer_state.get_print_history()
        assert len(history) > 0

        # Check that the content was processed (may be truncated by printer limits)
        last_job = history[-1]
        assert last_job.content_type == "text"

    @pytest.mark.asyncio
    async def test_special_characters_and_unicode(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test handling of special characters and Unicode content."""
        # Test various Unicode characters
        unicode_text = "Hello 世界 🌍 Привет ¡Hola! ñáéíóú"
        special_chars = "!@#$%^&*()_+-=[]{}|;':\",./<>?"

        test_cases = [
            unicode_text,
            special_chars,
            "Café résumé naïve",  # Accented characters
            "Line 1\nLine 2\tTabbed",  # Control characters
            "",  # Empty string
        ]

        printer_state = virtual_printer.printer_state

        for i, test_text in enumerate(test_cases):
            await printer_state.update_state_sync('text', test_text.encode('utf-8', errors='replace'), {})
            history = await printer_state.get_print_history()
            assert len(history) >= i + 1

    @pytest.mark.asyncio
    async def test_empty_and_null_parameters(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test behavior with empty, null, or invalid parameters."""
        printer_state = virtual_printer.printer_state

        # Test with None values
        await printer_state.update_state_sync('text', b'', {})
        await printer_state.update_state_sync('text', None, {})  # Should handle gracefully

        # Test with empty parameters dict
        await printer_state.update_state_sync('feed', b'', {})
        await printer_state.update_state_sync('cut', b'', {})

        # Verify no crashes occurred
        status = await printer_state.get_status()
        assert 'online' in status

    @pytest.mark.asyncio
    async def test_parameter_boundary_values(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test parameter values at their maximum and minimum limits."""
        printer_state = virtual_printer.printer_state

        # Test feed with maximum lines
        await printer_state.update_state_sync('feed', b'', {'lines': 255})

        # Test feed with minimum lines
        await printer_state.update_state_sync('feed', b'', {'lines': 0})

        # Test cut with various modes
        await printer_state.update_state_sync('cut', b'', {'mode': 'full'})
        await printer_state.update_state_sync('cut', b'', {'mode': 'partial'})
        await printer_state.update_state_sync('cut', b'', {'mode': 'invalid'})  # Should handle gracefully

    @pytest.mark.asyncio
    async def test_malformed_escpos_commands(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test handling of malformed or invalid ESCPOS commands."""
        printer_state = virtual_printer.printer_state

        # Test incomplete ESC sequences
        malformed_commands = [
            b'\x1b',  # Just ESC
            b'\x1b\x40',  # Valid initialize
            b'\x1b\x99',  # Invalid command
            b'\x1d\x99',  # Invalid GS command
            b'\x1b\x21\x01\x02\x03',  # Overlong command
        ]

        for cmd in malformed_commands:
            # These should not crash the parser
            try:
                await printer_state.update_state_sync('unknown', cmd, {})
            except Exception:
                # Some malformed commands might raise exceptions, that's OK
                pass

        # Verify printer is still functional
        status = await printer_state.get_status()
        assert status['online'] is True

    @pytest.mark.asyncio
    async def test_buffer_overflow_scenarios(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test buffer overflow and memory management scenarios."""
        printer_state = virtual_printer.printer_state

        # Send many small commands to potentially fill buffers
        for i in range(100):
            text = f"Line {i}: " + "x" * 100
            await printer_state.update_state_sync('text', text.encode(), {})

        # Send a cut command to process the buffer
        await printer_state.update_state_sync('cut', b'', {'mode': 'full'})

        # Verify the printer handled the load
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test concurrent print operations and thread safety."""
        printer_state = virtual_printer.printer_state

        async def send_text(text_id: int) -> int:
            text = f"Concurrent text {text_id}"
            await printer_state.update_state_sync('text', text.encode(), {})
            return text_id

        # Send multiple concurrent operations
        tasks = [send_text(i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Verify all operations completed
        assert len(results) == 10
        assert set(results) == set(range(10))

    @pytest.mark.asyncio
    async def test_rapid_succession_operations(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test rapid succession of print operations."""
        printer_state = virtual_printer.printer_state

        # Send operations in rapid succession without delays
        for i in range(50):
            text = f"Rapid {i}"
            await printer_state.update_state_sync('text', text.encode(), {})

            if i % 10 == 0:  # Every 10th operation, send a cut
                await printer_state.update_state_sync('cut', b'', {'mode': 'partial'})

        # Verify all operations were processed
        await printer_state.get_print_history()
        status = await printer_state.get_status()
        assert status['online'] is True

    @pytest.mark.asyncio
    async def test_extremely_long_lines(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test printing extremely long lines that exceed typical printer width."""
        printer_state = virtual_printer.printer_state

        # Create a line longer than typical printer width (80 chars is common max)
        long_line = "x" * 200 + " END"

        await printer_state.update_state_sync('text', long_line.encode(), {})

        # Verify it was processed (may be truncated by real printer)
        history = await printer_state.get_print_history()
        assert len(history) >= 1

    @pytest.mark.asyncio
    async def test_binary_data_handling(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test handling of binary data mixed with text."""
        printer_state = virtual_printer.printer_state

        # Mix of text and binary data
        binary_data = b'Hello\x00World\x01Test\x02Binary'

        await printer_state.update_state_sync('text', binary_data, {})

        # Verify it was processed without crashing
        history = await printer_state.get_print_history()
        assert len(history) >= 1

    @pytest.mark.asyncio
    async def test_nested_async_operations(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test nested async operations and proper context handling."""
        printer_state = virtual_printer.printer_state

        async def nested_operation(level: int) -> int:
            if level > 0:
                # Recursive nested operation
                await nested_operation(level - 1)

            text = f"Nested level {level}"
            await printer_state.update_state_sync('text', text.encode(), {})
            return level

        # Test deeply nested operations
        result = await nested_operation(5)
        assert result == 5

        # Verify all operations completed
        history = await printer_state.get_print_history()
        assert len(history) >= 6  # One for each level plus initial

    @pytest.mark.asyncio
    async def test_printer_state_persistence(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test that printer state persists correctly across operations."""
        printer_state = virtual_printer.printer_state

        # Initial state
        initial_status = await printer_state.get_status()

        # Perform various operations
        await printer_state.update_state_sync('text', b'First', {})
        await printer_state.update_state_sync('feed', b'', {'lines': 2})
        await printer_state.update_state_sync('text', b'Second', {})
        await printer_state.update_state_sync('cut', b'', {'mode': 'full'})

        # Check state after operations
        final_status = await printer_state.get_status()

        # State should have changed appropriately
        assert final_status['print_history_count'] >= initial_status['print_history_count']
        assert final_status['command_log_count'] >= initial_status['command_log_count']
