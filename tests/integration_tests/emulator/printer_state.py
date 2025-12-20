"""Printer state management for the virtual ESCPOS printer emulator."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class PrintJob:
    """Represents a single print job with its metadata."""
    timestamp: datetime
    content_type: str
    data: Any
    parameters: dict[str, Any]

    def get_summary(self) -> str:
        """Get a human-readable summary of the print job."""
        return f"{self.content_type} at {self.timestamp.isoformat()}"

    def as_dict(self) -> dict[str, Any]:
        """Convert print job to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'content_type': self.content_type,
            'data': self.data,
            'parameters': self.parameters
        }


@dataclass
class Command:
    """Represents a parsed ESCPOS command."""
    timestamp: datetime
    command_type: str
    raw_data: bytes
    parameters: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Convert command to dictionary for serialization."""
        return {
            'timestamp': self.timestamp.isoformat(),
            'command_type': self.command_type,
            'raw_data': self.raw_data.hex(),
            'parameters': self.parameters
        }


class PrinterState:
    """Manages the state of the virtual ESCPOS printer."""

    def __init__(self) -> None:
        """Initialize printer state."""
        self.online: bool = True
        self.paper_status: str = "loaded"
        self.buffer: list[bytes] = []
        self.print_history: list[PrintJob] = []
        self.command_log: list[Command] = []
        self._lock = asyncio.Lock()
        # Timestamp (loop time) of the last received text command
        self._last_text_time: float | None = None

    async def update_state(self, command: Command) -> None:
        """Update printer state based on received command."""
        async with self._lock:
            # Coalesce consecutive text commands into a single logical entry
            if command.command_type == "text":
                now = asyncio.get_event_loop().time()
                recent_text = (
                    self._last_text_time is not None and (now - self._last_text_time) < 0.005
                )
                force_new = bool(command.parameters.get("__force_new__")) if isinstance(command.parameters, dict) else False
                # If this is a mirrored reflection and we very recently recorded a text op,
                # drop this duplicate to avoid double-counting (mirror + network).
                if isinstance(command.parameters, dict) and command.parameters.get("__mirrored__") and recent_text and self.command_log and self.command_log[-1].command_type == "text":
                    self._last_text_time = now
                    return
                if recent_text and (not force_new) and self.command_log and self.command_log[-1].command_type == "text":
                    # Merge into previous text command
                    self.command_log[-1].raw_data += command.raw_data
                    # Also extend the most recent text print job if present
                    if self.print_history and self.print_history[-1].content_type == "text":
                        # Append even if raw_data is empty to record the event boundary
                        self.print_history[-1].data += command.raw_data
                else:
                    self.command_log.append(command)
                    self.buffer.append(command.raw_data or b"")
                    # Record a text print job (even for empty payloads) so tests can assert events
                    await self._add_print_job("text", command.raw_data, command.parameters)
                self._last_text_time = now
                return

            # Default logging path for non-text commands
            self.command_log.append(command)

            # Update state based on command type
            if command.command_type == "cut":
                # Cut command processes buffer as print job
                if self.buffer:
                    await self._add_print_job("text", b"".join(self.buffer), command.parameters)
                    self.buffer.clear()
            elif command.command_type == "feed":
                # Feed commands are logged but don't create print jobs
                pass
            elif command.command_type == "qr":
                # QR commands create print jobs
                await self._add_print_job("qr", command.raw_data, command.parameters)
            elif command.command_type == "image":
                # Image commands create print jobs
                await self._add_print_job("image", command.raw_data, command.parameters)
            elif command.command_type == "barcode":
                # Barcode commands create print jobs
                await self._add_print_job("barcode", command.raw_data, command.parameters)

    async def get_status(self) -> dict[str, Any]:
        """Get current printer status."""
        async with self._lock:
            return {
                'online': self.online,
                'paper_status': self.paper_status,
                'buffer_size': len(self.buffer),
                'print_history_count': len(self.print_history),
                'command_log_count': len(self.command_log)
            }

    async def clear_buffer(self) -> None:
        """Clear the print buffer."""
        async with self._lock:
            self.buffer.clear()

    async def _add_print_job(self, content_type: str, data: bytes, parameters: dict[str, Any]) -> None:
        """Add a new print job to history."""
        job = PrintJob(
            timestamp=datetime.now(),
            content_type=content_type,
            data=data,
            parameters=parameters
        )
        self.print_history.append(job)

    async def simulate_error(self, error_type: str) -> None:
        """Simulate a printer error condition."""
        async with self._lock:
            if error_type == "offline":
                self.online = False
            elif error_type == "paper_out":
                self.paper_status = "out"
            elif error_type == "paper_jam":
                self.paper_status = "jammed"
            elif error_type == "reset":
                self.online = True
                self.paper_status = "loaded"
                self.buffer.clear()

    async def get_print_history(self) -> list[PrintJob]:
        """Get the complete print history."""
        async with self._lock:
            return self.print_history.copy()

    async def get_command_log(self) -> list[Command]:
        """Get the complete command log."""
        async with self._lock:
            return self.command_log.copy()

    async def clear_history(self) -> None:
        """Clear print history and command log."""
        async with self._lock:
            self.print_history.clear()
            self.command_log.clear()
            self.buffer.clear()
            # Reset text timing to prevent stale state affecting future commands
            self._last_text_time = None

    async def update_state_sync(self, command_type: str, data: bytes, parameters: dict[str, Any]) -> None:
        """Compatibility wrapper used by tests to update state.

        Implemented as an async method so tests can `await` it directly.
        """
        # Coerce None payloads to empty bytes for robustness
        data = data or b""
        # Include force-new marker for text to avoid merging in concurrent scenarios
        params = dict(parameters)
        if command_type == "text":
            params["__force_new__"] = True
        command = Command(
            timestamp=datetime.now(),
            command_type=command_type,
            raw_data=data,
            parameters=params
        )
        # Ensure each sync invocation starts a new logical block for text
        if command_type == "text":
            self.start_new_text_block()
        # Simulate minimal processing latency for more realistic timings
        try:
            await asyncio.sleep(0.002)
        except Exception:
            pass
        await self.update_state(command)

    def start_new_text_block(self) -> None:
        """Force the next text command to start a new logical block."""
        # Set last text time far in the past so the next text does not merge
        self._last_text_time = None
