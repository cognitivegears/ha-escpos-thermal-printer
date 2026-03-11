"""CUPS printer adapter implementation."""

from __future__ import annotations

import contextlib
import logging
import os
import tempfile
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import sanitize_log_message
from .base_adapter import EscposPrinterAdapterBase
from .config import CupsPrinterConfig

_LOGGER = logging.getLogger(__name__)


# Late imports to avoid import errors at HA startup if deps pending
def _get_dummy_printer() -> type[Any]:
    """Get the Dummy printer class for building ESC/POS commands."""
    from escpos.printer import Dummy  # noqa: PLC0415

    return Dummy  # type: ignore[no-any-return]


def _get_cups_connection(server: str | None = None) -> Any:
    """Get a CUPS connection, optionally to a remote server.

    Args:
        server: CUPS server address (e.g., 'hostname' or 'hostname:port').
                If None, connects to localhost.

    Returns:
        cups.Connection object.
    """
    import cups  # noqa: PLC0415

    # Always explicitly set the server to avoid stale global state from previous calls.
    # pycups stores the server globally, so we must reset it every time.
    cups.setServer(server or "")
    return cups.Connection()


def _submit_to_cups(printer_name: str, data: bytes, server: str | None = None) -> int:
    """Submit raw data to CUPS printer.

    Args:
        printer_name: Name of the CUPS printer.
        data: Raw ESC/POS data to print.
        server: CUPS server address (optional).

    Returns:
        CUPS job ID.
    """
    conn = _get_cups_connection(server)

    # Write data to a temporary file and submit to CUPS
    with tempfile.NamedTemporaryFile(delete=False, suffix=".raw") as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        # Submit the raw file to CUPS
        # Use 'raw' option to tell CUPS to send data as-is without filtering
        job_id: int = conn.printFile(
            printer_name,
            tmp_path,
            "ESC/POS Print Job",
            {"raw": "true"},
        )
        _LOGGER.debug("Submitted CUPS job %d to printer '%s'", job_id, printer_name)
        return job_id
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def is_cups_available(server: str | None = None) -> bool:
    """Check if CUPS is available on the system.

    Args:
        server: CUPS server address. If None, connects to localhost.

    Returns:
        True if CUPS/pycups is available, False otherwise.
    """
    try:
        _get_cups_connection(server)
    except ImportError:
        _LOGGER.warning("pycups library not available - CUPS printing disabled")
        return False
    except Exception as e:
        _LOGGER.warning("CUPS not available: %s", sanitize_log_message(str(e)))
        return False
    else:
        return True


def get_cups_printers(server: str | None = None) -> list[str]:
    """Get list of available CUPS printers.

    Args:
        server: CUPS server address. If None, connects to localhost.

    Returns:
        List of CUPS printer names.
    """
    try:
        conn = _get_cups_connection(server)
        printers = conn.getPrinters()
    except ImportError:
        _LOGGER.warning("pycups library not available")
        return []
    except Exception as e:
        _LOGGER.warning("Failed to get CUPS printers: %s", sanitize_log_message(str(e)))
        return []
    else:
        return list(printers.keys())


def is_cups_printer_available(printer_name: str, server: str | None = None) -> bool:
    """Check if a CUPS printer exists.

    Args:
        printer_name: Name of the CUPS printer to check.
        server: CUPS server address. If None, connects to localhost.

    Returns:
        True if printer exists, False otherwise.
    """
    try:
        conn = _get_cups_connection(server)
        printers = conn.getPrinters()
    except ImportError:
        _LOGGER.warning("pycups library not available")
        return False
    except Exception as e:
        _LOGGER.warning(
            "Failed to check CUPS printer: %s", sanitize_log_message(str(e))
        )
        return False
    else:
        return printer_name in printers


def get_cups_printer_status(
    printer_name: str, server: str | None = None
) -> tuple[bool, str | None]:
    """Get status of a CUPS printer.

    Args:
        printer_name: Name of the CUPS printer.
        server: CUPS server address. If None, connects to localhost.

    Returns:
        Tuple of (is_available, error_message).
    """
    try:
        conn = _get_cups_connection(server)
        printers = conn.getPrinters()
    except ImportError:
        return False, "pycups library not available"
    except Exception as e:
        return False, str(e)

    if printer_name not in printers:
        return False, "Printer not found"

    printer_info = printers[printer_name]
    # CUPS printer states: 3=idle, 4=processing, 5=stopped
    state = printer_info.get("printer-state", 0)
    state_reasons = printer_info.get("printer-state-reasons", [])

    if state == 5:  # Stopped
        reason = state_reasons[0] if state_reasons else "Printer stopped"
        return False, str(reason)

    # Check for error states in reasons
    if state_reasons and state_reasons != ["none"]:
        for reason in state_reasons:
            if "error" in str(reason).lower():
                return False, str(reason)

    return True, None


class CupsPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for CUPS-managed ESC/POS printers.

    Uses a Dummy printer to buffer ESC/POS commands, then submits the raw
    data to CUPS via pycups. This allows printing through CUPS-managed
    queues without requiring direct network/USB access.
    """

    def __init__(self, config: CupsPrinterConfig) -> None:
        super().__init__(config)
        self._cups_config = config

    @property
    def config(self) -> CupsPrinterConfig:
        """Return the CUPS printer configuration."""
        return self._cups_config

    async def start(
        self, hass: HomeAssistant, *, keepalive: bool, status_interval: int
    ) -> None:
        """Start the adapter. Keepalive is forced off for CUPS/Dummy approach."""
        # Force keepalive off — Dummy printers buffer commands per-job
        await super().start(hass, keepalive=False, status_interval=status_interval)

    def _connect(self) -> Any:
        """Create a Dummy printer to collect ESC/POS commands."""
        dummy_class = _get_dummy_printer()
        profile_obj = self._get_profile_obj()
        return dummy_class(profile=profile_obj)

    async def _release_printer(
        self, hass: HomeAssistant, printer: Any, *, owned: bool
    ) -> None:
        """Submit buffered data to CUPS before releasing the Dummy printer."""
        if owned and hasattr(printer, "output") and printer.output:
            data = printer.output
            _LOGGER.debug(
                "Submitting %d bytes to CUPS printer '%s'",
                len(data),
                self._cups_config.printer_name,
            )
            await hass.async_add_executor_job(
                _submit_to_cups,
                self._cups_config.printer_name,
                data,
                self._cups_config.cups_server,
            )
        await super()._release_printer(hass, printer, owned=owned)

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Check CUPS printer status via pycups."""

        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            ok, err = get_cups_printer_status(
                self._cups_config.printer_name, self._cups_config.cups_server
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            return ok, err, latency_ms

        ok, err, latency_ms = await hass.async_add_executor_job(_probe)
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "unavailable")
        if self._status != ok:
            self._status = ok
            if not ok:
                _LOGGER.warning(
                    "CUPS printer '%s' not available: %s",
                    self._cups_config.printer_name,
                    err,
                )
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        if self._cups_config.cups_server:
            return f"CUPS:{self._cups_config.cups_server}/{self._cups_config.printer_name}"
        return f"CUPS:{self._cups_config.printer_name}"
