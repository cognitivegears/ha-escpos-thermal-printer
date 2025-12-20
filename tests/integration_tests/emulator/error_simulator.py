"""Advanced error simulation for the virtual ESCPOS printer emulator."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
import random
from typing import Any

_LOGGER = logging.getLogger(__name__)


@dataclass
class ErrorCondition:
    """Represents a programmable error condition."""
    error_type: str
    trigger_type: str  # 'immediate', 'after_commands', 'after_time', 'random'
    trigger_value: Any  # Number of commands, seconds, probability
    duration: float | None = None  # How long the error lasts (None = permanent)
    recovery_type: str = 'manual'  # 'manual', 'auto', 'conditional'
    recovery_condition: Callable | None = None

    def should_trigger(self, command_count: int, elapsed_time: float) -> bool:
        """Check if this error condition should be triggered."""
        if self.trigger_type == 'immediate':
            return True
        elif self.trigger_type == 'after_commands':
            return bool(command_count >= self.trigger_value)
        elif self.trigger_type == 'after_time':
            return bool(elapsed_time >= self.trigger_value)
        elif self.trigger_type == 'random':
            return bool(random.random() < self.trigger_value)
        return False

    def should_recover(self, **kwargs: Any) -> bool:
        """Check if this error should recover."""
        if self.recovery_type == 'auto' and self.duration:
            return bool(kwargs.get('elapsed_since_error', 0) >= self.duration)
        elif self.recovery_type == 'conditional' and self.recovery_condition:
            return bool(self.recovery_condition(**kwargs))
        return False


class ErrorSimulator:
    """Advanced error simulator for the virtual printer."""

    def __init__(self) -> None:
        """Initialize the error simulator."""
        self.active_errors: dict[str, ErrorCondition] = {}
        self.error_history: list[dict[str, Any]] = []
        self.command_count = 0
        self.start_time = asyncio.get_event_loop().time()
        self._lock = asyncio.Lock()

    async def add_error_condition(self, condition: ErrorCondition) -> None:
        """Add a programmable error condition."""
        async with self._lock:
            self.active_errors[condition.error_type] = condition
            _LOGGER.info("Added error condition: %s", condition.error_type)

    async def remove_error_condition(self, error_type: str) -> None:
        """Remove an error condition."""
        async with self._lock:
            if error_type in self.active_errors:
                del self.active_errors[error_type]
                _LOGGER.info("Removed error condition: %s", error_type)

    async def trigger_error(self, error_type: str) -> None:
        """Manually trigger an error condition."""
        async with self._lock:
            if error_type in self.active_errors:
                condition = self.active_errors[error_type]
                await self._activate_error(condition)
            else:
                # Create and activate a temporary error
                temp_condition = ErrorCondition(
                    error_type=error_type,
                    trigger_type='immediate',
                    trigger_value=None
                )
                await self._activate_error(temp_condition)

    async def clear_all_errors(self) -> None:
        """Clear all active error conditions."""
        async with self._lock:
            self.active_errors.clear()
            _LOGGER.info("Cleared all error conditions")

    async def process_command(self, command_type: str, **kwargs: Any) -> str | None:
        """Process a command and check for error triggers."""
        async with self._lock:
            self.command_count += 1
            current_time = asyncio.get_event_loop().time()
            elapsed_time = current_time - self.start_time

            # Check for error triggers; allow multiple activations in the same cycle
            first_error: str | None = None
            for error_type, condition in list(self.active_errors.items()):
                if condition.should_trigger(self.command_count, elapsed_time):
                    await self._activate_error(condition)
                    if first_error is None:
                        first_error = error_type

            # Check for error recovery
            for error_type, condition in list(self.active_errors.items()):
                if condition.should_recover(
                    elapsed_since_error=kwargs.get('elapsed_since_error', 0),
                    command_type=command_type,
                    **kwargs
                ):
                    await self._recover_error(error_type)

            return first_error

    async def _activate_error(self, condition: ErrorCondition) -> None:
        """Activate an error condition."""
        error_record = {
            'timestamp': asyncio.get_event_loop().time(),
            'error_type': condition.error_type,
            'action': 'activated',
            'condition': {
                'trigger_type': condition.trigger_type,
                'trigger_value': condition.trigger_value,
                'duration': condition.duration
            }
        }
        self.error_history.append(error_record)
        _LOGGER.info("Activated error: %s", condition.error_type)

    async def _recover_error(self, error_type: str) -> None:
        """Recover from an error condition."""
        if error_type in self.active_errors:
            condition = self.active_errors[error_type]

            error_record = {
                'timestamp': asyncio.get_event_loop().time(),
                'error_type': error_type,
                'action': 'recovered',
                'condition': {
                    'recovery_type': condition.recovery_type,
                    'duration': condition.duration
                }
            }
            self.error_history.append(error_record)

            # Remove the error condition if it's set to auto-recover
            if condition.recovery_type in ('auto', 'conditional'):
                del self.active_errors[error_type]

            _LOGGER.info("Recovered from error: %s", error_type)

    async def get_active_errors(self) -> list[str]:
        """Get list of currently active error types."""
        async with self._lock:
            return list(self.active_errors.keys())

    async def get_error_history(self) -> list[dict[str, Any]]:
        """Get the complete error history."""
        async with self._lock:
            return self.error_history.copy()

    async def reset(self) -> None:
        """Reset the error simulator to initial state."""
        async with self._lock:
            self.active_errors.clear()
            self.error_history.clear()
            self.command_count = 0
            self.start_time = asyncio.get_event_loop().time()
            _LOGGER.info("Error simulator reset")


# Predefined error conditions for common scenarios
def create_offline_error(trigger_type: str = 'immediate', trigger_value: Any = None,
                        duration: float | None = None) -> ErrorCondition:
    """Create a printer offline error condition."""
    return ErrorCondition(
        error_type='offline',
        trigger_type=trigger_type,
        trigger_value=trigger_value,
        duration=duration,
        recovery_type='manual'
    )


def create_paper_out_error(trigger_type: str = 'after_commands', trigger_value: int = 5,
                          duration: float | None = None) -> ErrorCondition:
    """Create a paper out error condition."""
    return ErrorCondition(
        error_type='paper_out',
        trigger_type=trigger_type,
        trigger_value=trigger_value,
        duration=duration,
        recovery_type='manual'
    )


def create_timeout_error(trigger_type: str = 'random', trigger_value: float = 0.1,
                        duration: float = 2.0) -> ErrorCondition:
    """Create a timeout error condition."""
    return ErrorCondition(
        error_type='timeout',
        trigger_type=trigger_type,
        trigger_value=trigger_value,
        duration=duration,
        recovery_type='auto'
    )


def create_connection_error(trigger_type: str = 'after_time', trigger_value: float = 30.0,
                           duration: float = 5.0) -> ErrorCondition:
    """Create a connection error condition."""
    return ErrorCondition(
        error_type='connection_error',
        trigger_type=trigger_type,
        trigger_value=trigger_value,
        duration=duration,
        recovery_type='auto'
    )


def create_intermittent_error(error_type: str, interval: float = 10.0,
                             duration: float = 2.0) -> ErrorCondition:
    """Create an intermittent error that occurs at regular intervals."""
    def recovery_condition(**kwargs: Any) -> bool:
        elapsed: float = float(kwargs.get('elapsed_since_error', 0))
        return bool(elapsed >= duration)

    return ErrorCondition(
        error_type=error_type,
        trigger_type='after_time',
        trigger_value=interval,
        duration=duration,
        recovery_type='conditional',
        recovery_condition=recovery_condition
    )
