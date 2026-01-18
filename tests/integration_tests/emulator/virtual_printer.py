"""Virtual ESCPOS printer emulator with TCP server."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any

from .command_parser import EscposCommandParser
from .error_simulator import ErrorSimulator
from .printer_state import PrinterState

_LOGGER = logging.getLogger(__name__)


class ClientConnection:
    """Represents a client connection to the virtual printer."""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
                 printer_state: PrinterState, command_parser: EscposCommandParser,
                 error_simulator: ErrorSimulator | None = None) -> None:
        """Initialize client connection."""
        self.reader = reader
        self.writer = writer
        self.printer_state = printer_state
        self.command_parser = command_parser
        self.client_address = writer.get_extra_info('peername')
        self.error_simulator = error_simulator
        self._running = True

    async def handle_client(self) -> None:
        """Handle communication with the connected client."""
        _LOGGER.info("Client connected: %s", self.client_address)

        try:
            while self._running:
                # Read data from client
                data = await self.reader.read(1024)
                if not data:
                    # Client disconnected
                    break

                _LOGGER.debug("Received data from %s: %s", self.client_address, data.hex())

                # Parse and process commands
                await self._process_data(data)

        except Exception as exc:
            _LOGGER.exception("Error handling client %s: %s", self.client_address, exc)
        finally:
            _LOGGER.info("Client disconnected: %s", self.client_address)
            self.writer.close()
            await self.writer.wait_closed()

    async def _process_data(self, data: bytes) -> None:
        """Process received data and update printer state."""
        # Parse and process all commands from the buffered data
        from datetime import datetime

        from .printer_state import Command

        command = self.command_parser.parse_command(data)
        while command:
            _LOGGER.debug("Parsed command: %s", command)
            cmd_obj = Command(
                timestamp=datetime.now(),
                command_type=command['type'],
                raw_data=command['raw_data'],
                parameters=command['parameters']
            )
            if self.error_simulator is not None:
                with contextlib.suppress(Exception):
                    await self.error_simulator.process_command(command['type'])
            await self.printer_state.update_state(cmd_obj)
            # Simulate minimal processing time to better reflect real devices
            with contextlib.suppress(Exception):
                await asyncio.sleep(0.002)
            await self._send_response(command)
            # Parse next command from buffer (no new data)
            command = self.command_parser.parse_command(b"")

    async def _send_response(self, command: dict) -> None:
        """Send appropriate response based on command type."""
        # Most ESCPOS commands don't require responses, but some do
        # For now, we'll implement basic responses for status queries

        if command['type'] == 'status_request':
            # Send printer status response
            status = await self.printer_state.get_status()
            response = self._create_status_response(status)
            self.writer.write(response)
            await self.writer.drain()

    def _create_status_response(self, status: dict) -> bytes:
        """Create a status response byte sequence."""
        # This is a simplified status response
        # Real printers have specific status byte formats
        status_byte = 0x00

        if not status['online']:
            status_byte |= 0x08  # Offline bit
        if status['paper_status'] != 'loaded':
            status_byte |= 0x20  # Paper error bit

        return bytes([status_byte])

    def disconnect(self) -> None:
        """Disconnect the client."""
        self._running = False


class VirtualPrinterServer:
    """Virtual ESCPOS printer server that emulates a thermal printer."""

    def __init__(self, host: str = '127.0.0.1', port: int = 9100, timeout: float = 5.0) -> None:
        """Initialize the virtual printer server."""
        self.host = host
        self.port = port
        self.timeout = timeout
        self.server: asyncio.AbstractServer | None = None
        self.clients: list[ClientConnection] = []
        self.printer_state = PrinterState()
        self.command_parser = EscposCommandParser()
        self._running = False
        self.error_simulator = ErrorSimulator()

    async def start(self) -> None:
        """Start the virtual printer server."""
        if self._running:
            _LOGGER.warning("Server is already running")
            return

        _LOGGER.info("Starting virtual printer server on %s:%s", self.host, self.port)

        try:
            self.server = await asyncio.start_server(
                self._handle_connection,
                self.host,
                self.port
            )

            self._running = True
            _LOGGER.info("Virtual printer server started successfully")

            # Keep the server running
            async with self.server:
                await self.server.serve_forever()

        except Exception as exc:
            _LOGGER.exception("Failed to start virtual printer server: %s", exc)
            raise

    async def stop(self) -> None:
        """Stop the virtual printer server."""
        if not self._running:
            return

        _LOGGER.info("Stopping virtual printer server")

        # Disconnect all clients
        for client in self.clients[:]:  # Copy list to avoid modification during iteration
            client.disconnect()

        # Close server
        if self.server:
            self.server.close()
            await self.server.wait_closed()

        self._running = False
        _LOGGER.info("Virtual printer server stopped")

    async def _handle_connection(self, reader: asyncio.StreamReader,
                                writer: asyncio.StreamWriter) -> None:
        """Handle a new client connection."""
        # Reject connections if offline error active
        try:
            if self.error_simulator is not None:
                active = await self.error_simulator.get_active_errors()
                if 'offline' in active:
                    _LOGGER.info("Rejecting connection while offline: %s", writer.get_extra_info('peername'))
                    writer.close()
                    await writer.wait_closed()
                    return
        except Exception:
            pass
        client = ClientConnection(reader, writer, self.printer_state, self.command_parser, self.error_simulator)
        self.clients.append(client)

        try:
            await client.handle_client()
        finally:
            # Remove client from list when connection ends
            if client in self.clients:
                self.clients.remove(client)

    async def simulate_error(self, error_type: str) -> None:
        """Simulate a printer error condition."""
        # Record error via the error simulator for history/visibility
        try:
            if self.error_simulator is not None:
                await self.error_simulator.trigger_error(error_type)
        except Exception:
            pass
        # Reflect error in the printer state for behavior
        await self.printer_state.simulate_error(error_type)
        _LOGGER.info("Simulated printer error: %s", error_type)

    async def get_print_history(self) -> list:
        """Get the complete print history."""
        return await self.printer_state.get_print_history()

    async def get_command_log(self) -> list:
        """Get the complete command log."""
        return await self.printer_state.get_command_log()

    async def get_status(self) -> dict:
        """Get current printer status."""
        return await self.printer_state.get_status()

    async def clear_history(self) -> None:
        """Clear print history and command log."""
        await self.printer_state.clear_history()
        self.command_parser.clear_buffer()
        _LOGGER.info("Printer history and buffers cleared")

    async def reset(self) -> None:
        """Reset the printer to initial state."""
        await self.printer_state.simulate_error("reset")
        self.command_parser.clear_buffer()
        _LOGGER.info("Printer reset to initial state")

    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._running

    def get_client_count(self) -> int:
        """Get the number of connected clients."""
        return len(self.clients)


# Context manager support
class VirtualPrinter:
    """Context manager for the virtual printer server."""

    def __init__(self, host: str = '127.0.0.1', port: int = 9100, timeout: float = 5.0) -> None:
        """Initialize the virtual printer context manager."""
        self.server = VirtualPrinterServer(host, port, timeout)
        self._task: asyncio.Task | None = None

    async def __aenter__(self) -> VirtualPrinterServer:
        """Start the virtual printer server."""
        self._task = asyncio.create_task(self.server.start())
        # Give the server a moment to start
        await asyncio.sleep(0.1)
        return self.server

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Stop the virtual printer server."""
        await self.server.stop()
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
