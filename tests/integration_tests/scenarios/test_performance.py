"""Performance and load testing for ESCPOS printer integration."""

import asyncio
import time

import pytest

from tests.integration_tests.fixtures import MockDataGenerator


class TestPerformance:
    """Test performance characteristics and load handling."""

    @pytest.mark.asyncio
    async def test_concurrent_print_jobs(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test handling of multiple concurrent print jobs."""
        printer_state = virtual_printer.printer_state

        # Create multiple concurrent print tasks
        async def print_job(job_id: int) -> int:
            text = MockDataGenerator.generate_text_content(100)  # 100 chars each
            await printer_state.update_state_sync('text', text.encode(), {})
            if job_id % 5 == 0:  # Every 5th job, feed paper
                await printer_state.update_state_sync('feed', b'', {'lines': 1})
            return job_id

        # Launch 20 concurrent print jobs
        start_time = time.time()
        tasks = [print_job(i) for i in range(20)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # Verify all jobs completed
        assert len(results) == 20
        assert set(results) == set(range(20))

        # Verify reasonable performance (should complete in reasonable time)
        duration = end_time - start_time
        assert duration < 5.0  # Should complete within 5 seconds

        # Check printer state
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_high_frequency_operations(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test rapid succession of print operations."""
        printer_state = virtual_printer.printer_state

        # Measure time for 100 rapid operations
        start_time = time.time()

        for i in range(100):
            text = f"Rapid operation {i}"
            await printer_state.update_state_sync('text', text.encode(), {})

            # Every 10 operations, perform a cut
            if i % 10 == 0:
                await printer_state.update_state_sync('cut', b'', {'mode': 'partial'})

        end_time = time.time()
        duration = end_time - start_time

        # Verify performance - should handle high frequency well
        operations_per_second = 100 / duration
        assert operations_per_second > 10  # At least 10 ops/sec

        # Verify printer remained stable
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_memory_usage_under_load(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test memory usage patterns under load."""
        printer_state = virtual_printer.printer_state

        # Generate large amounts of print data
        large_texts = []
        for i in range(50):
            # Create progressively larger texts
            size = 500 + (i * 100)  # 500 to 5500 chars each
            text = MockDataGenerator.generate_text_content(size)
            large_texts.append(text)

        # Process all large texts
        for i, text in enumerate(large_texts):
            await printer_state.update_state_sync('text', text.encode(), {})

            # Process buffer periodically to prevent overflow
            if i % 10 == 0:
                await printer_state.update_state_sync('cut', b'', {'mode': 'full'})

        # Verify printer handled large data load
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_batch_processing_efficiency(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test efficiency of batch processing operations."""
        printer_state = virtual_printer.printer_state

        # Prepare batch of print data
        batch_size = 25
        batch_data = []

        for _i in range(batch_size):
            qr_data = MockDataGenerator.generate_qr_data()
            barcode_data = MockDataGenerator.generate_barcode_data()
            text_data = MockDataGenerator.generate_text_content(200)

            batch_data.append({
                'qr': qr_data,
                'barcode': barcode_data,
                'text': text_data
            })

        # Process batch efficiently
        start_time = time.time()

        for item in batch_data:
            await printer_state.update_state_sync('qr', item['qr'].encode(), {})
            await printer_state.update_state_sync('barcode', item['barcode'].encode(), {'bc': 'CODE128'})
            await printer_state.update_state_sync('text', item['text'].encode(), {})
            await printer_state.update_state_sync('cut', b'', {'mode': 'partial'})

        end_time = time.time()
        duration = end_time - start_time

        # Calculate processing rate
        total_operations = batch_size * 4  # qr + barcode + text + cut per item
        operations_per_second = total_operations / duration

        # Verify reasonable batch processing performance
        assert operations_per_second > 5  # At least 5 operations per second

        # Verify all operations completed successfully
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) >= batch_size  # At least one print job per batch item

    @pytest.mark.asyncio
    async def test_resource_cleanup_under_load(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test proper resource cleanup during high load operations."""
        printer_state = virtual_printer.printer_state

        # Generate high load with multiple operation types
        operations = []
        for _i in range(30):
            operations.extend([
                ('text', MockDataGenerator.generate_text_content(150).encode(), {}),
                ('qr', MockDataGenerator.generate_qr_data().encode(), {}),
                ('feed', b'', {'lines': 1}),
            ])

        # Execute operations
        for op_type, data, params in operations:
            await printer_state.update_state_sync(op_type, data, params)

        # Trigger final cut to process remaining buffer
        await printer_state.update_state_sync('cut', b'', {'mode': 'full'})

        # Clear history to test cleanup
        await printer_state.clear_history()

        # Verify cleanup worked
        status = await printer_state.get_status()
        assert status['print_history_count'] == 0
        assert status['command_log_count'] == 0
        assert status['buffer_size'] == 0

        # Verify printer still functional after cleanup
        await printer_state.update_state_sync('text', b'Post-cleanup test', {})
        final_status = await printer_state.get_status()
        assert final_status['online'] is True

    @pytest.mark.asyncio
    async def test_thread_safety_under_concurrency(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test thread safety when multiple threads access printer concurrently."""
        printer_state = virtual_printer.printer_state

        async def concurrent_worker(worker_id: int, num_operations: int) -> tuple[int, int]:
            """Worker function that performs multiple operations."""
            for i in range(num_operations):
                text = f"Worker {worker_id}, Op {i}"
                await printer_state.update_state_sync('text', text.encode(), {})

                if i % 3 == 0:  # Occasional feed/cut operations
                    await printer_state.update_state_sync('feed', b'', {'lines': 1})

            return worker_id, num_operations

        # Launch multiple concurrent workers
        num_workers = 5
        operations_per_worker = 10

        start_time = time.time()
        tasks = [concurrent_worker(i, operations_per_worker) for i in range(num_workers)]
        results = await asyncio.gather(*tasks)
        end_time = time.time()

        # Verify all workers completed
        assert len(results) == num_workers
        for _worker_id, ops_completed in results:
            assert ops_completed == operations_per_worker

        # Check performance
        duration = end_time - start_time
        total_operations = num_workers * operations_per_worker
        operations_per_second = total_operations / duration

        # Verify reasonable concurrent performance
        assert operations_per_second > 8  # At least 8 operations per second

        # Verify printer state integrity
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) > 0

    @pytest.mark.asyncio
    async def test_response_time_consistency(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test that response times remain consistent under load."""
        printer_state = virtual_printer.printer_state

        response_times = []

        # Measure response time for multiple operations
        for i in range(50):
            start_time = time.time()
            text = f"Timing test {i}"
            await printer_state.update_state_sync('text', text.encode(), {})
            end_time = time.time()

            response_times.append(end_time - start_time)

        # Calculate statistics
        avg_response_time = sum(response_times) / len(response_times)
        max_response_time = max(response_times)
        min_response_time = min(response_times)

        # Verify response time consistency
        # Average should be reasonable (< 0.1 seconds per operation)
        assert avg_response_time < 0.1

        # Max should not be excessively high (should be < 1 second)
        assert max_response_time < 1.0

        # Min should be reasonable (> 0.001 seconds)
        assert min_response_time > 0.001

        # Variance should be reasonable (max/min ratio < 10)
        if min_response_time > 0:
            response_ratio = max_response_time / min_response_time
            assert response_ratio < 10

    @pytest.mark.asyncio
    async def test_scalability_with_increasing_load(self, virtual_printer) -> None:  # type: ignore[no-untyped-def]
        """Test how performance scales with increasing load."""
        printer_state = virtual_printer.printer_state

        scalability_results = []

        # Test with increasing batch sizes
        batch_sizes = [5, 10, 20, 50]

        for batch_size in batch_sizes:
            # Generate batch data
            batch_data = [MockDataGenerator.generate_text_content(100) for _ in range(batch_size)]

            # Time the batch processing
            start_time = time.time()
            for text in batch_data:
                await printer_state.update_state_sync('text', text.encode(), {})
            end_time = time.time()

            duration = end_time - start_time
            operations_per_second = batch_size / duration

            scalability_results.append({
                'batch_size': batch_size,
                'duration': duration,
                'ops_per_second': operations_per_second
            })

        # Verify scalability characteristics
        # Performance should be reasonably consistent or show expected scaling
        for result in scalability_results:
            # Each batch should process at reasonable speed
            assert result['ops_per_second'] > 5  # At least 5 operations per second

        # Verify printer remained stable throughout
        status = await printer_state.get_status()
        assert status['online'] is True

        history = await printer_state.get_print_history()
        assert len(history) >= sum(r['batch_size'] for r in scalability_results)
