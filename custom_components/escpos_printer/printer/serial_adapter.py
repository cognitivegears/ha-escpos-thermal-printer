"""Serial (UART/RS-232) printer adapter implementation."""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import stat
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import sanitize_log_message
from . import serial_transport
from ._escpos_serial import make_serial_escpos
from .base_adapter import EscposPrinterAdapterBase
from .config import SerialPrinterConfig

_LOGGER = logging.getLogger(__name__)

# Errnos that may be worth retrying on serial ports:
# EBUSY (16) — port held by another process that may release imminently
# EIO (5)    — transient I/O error on the port
_RETRYABLE_ERRNOS = {errno.EBUSY, errno.EIO}


def _is_url(port_or_url: str) -> bool:
    """Return True if the configured value is a URL (contains ``://``)."""
    return "://" in port_or_url


class SerialPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for serial (UART/RS-232) ESC/POS printers.

    Accepts both filesystem paths (``/dev/ttyUSB0``, ``COM3``) and serialx
    URL schemes (``esphome://host:port``, ``rfc2217://host:port``,
    ``socket://host:port``) via the ``serial_port`` config field.
    """

    _CONNECT_RETRIES = 2
    _CONNECT_RETRY_DELAY_S = 0.3

    default_chunk_delay_ms = 0

    def __init__(self, config: SerialPrinterConfig) -> None:
        super().__init__(config)
        self._serial_config = config
        # Serial ports behave like USB: one connection at a time, no persistent
        # keepalive. URL-based transports (ESPHome proxy, RFC2217) also need
        # reconnect-per-operation to avoid stale connections.
        self._keepalive = False

    @property
    def config(self) -> SerialPrinterConfig:
        """Return the serial printer configuration."""
        return self._serial_config

    def _connect(self) -> Any:
        """Open a serial transport and wrap it in a python-escpos printer."""
        profile_obj = self._get_profile_obj()
        last_exc: Exception | None = None
        port = self._serial_config.serial_port
        baudrate = self._serial_config.baudrate
        timeout = self._serial_config.timeout

        for attempt in range(self._CONNECT_RETRIES + 1):
            try:
                transport = serial_transport.open_serial_transport(port, baudrate, timeout)
            except Exception as exc:
                last_exc = exc
                err_no = getattr(exc, "errno", None)
                self._last_error_errno = err_no
                _LOGGER.debug(
                    "Serial open failed for %s (attempt %s/%s errno=%s): %s",
                    sanitize_log_message(port),
                    attempt + 1,
                    self._CONNECT_RETRIES + 1,
                    err_no,
                    sanitize_log_message(str(exc)),
                )
                retryable = err_no in _RETRYABLE_ERRNOS if err_no is not None else False
                if attempt >= self._CONNECT_RETRIES or not retryable:
                    _LOGGER.warning(
                        "Serial open failed for %s (errno=%s): %s",
                        sanitize_log_message(port),
                        err_no,
                        sanitize_log_message(str(exc)),
                    )
                    raise
                time.sleep(self._CONNECT_RETRY_DELAY_S)
                continue
            else:
                return make_serial_escpos(transport, profile_obj)

        assert last_exc is not None  # pragma: no cover
        raise last_exc

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Check serial printer reachability.

        For filesystem paths we do a non-invasive character-device check
        (``os.path.exists`` + ``stat.S_ISCHR``).  For URL-based connections
        (ESPHome proxy, RFC2217, socket) we attempt a brief open/close, since
        there is no device-file to inspect.

        Skips the check when a print operation currently holds the lock.
        """
        if self._lock.locked():
            _LOGGER.debug(
                "Skipping serial status probe for %s — print operation in flight",
                sanitize_log_message(self._serial_config.serial_port),
            )
            return

        port = self._serial_config.serial_port

        if _is_url(port):
            await self._status_check_url(hass, port)
        else:
            await self._status_check_path(hass, port)

    async def _status_check_path(self, hass: HomeAssistant, port: str) -> None:
        """Non-invasive status check for filesystem serial ports."""

        def _probe() -> tuple[bool, str | None, int | None, int | None]:
            start = time.perf_counter()
            try:
                st = os.stat(port)
            except OSError as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return False, str(exc), latency_ms, getattr(exc, "errno", None)
            else:
                latency_ms = int((time.perf_counter() - start) * 1000)
                if not stat.S_ISCHR(st.st_mode):
                    return False, f"{port} is not a character device", latency_ms, None
                return True, None, latency_ms, None

        ok, err, latency_ms, err_no = await hass.async_add_executor_job(_probe)
        self._record_status(ok, err, latency_ms, err_no)

    async def _status_check_url(self, hass: HomeAssistant, port: str) -> None:
        """Status check for URL-based serial connections via a brief open/close probe."""

        def _probe() -> tuple[bool, str | None, int | None, int | None]:
            start = time.perf_counter()
            probe_timeout = min(self._serial_config.timeout, 3.0)
            try:
                transport = serial_transport.open_serial_transport(
                    port,
                    self._serial_config.baudrate,
                    probe_timeout,
                )
            except OSError as exc:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return False, str(exc), latency_ms, getattr(exc, "errno", None)
            else:
                latency_ms = int((time.perf_counter() - start) * 1000)
                with contextlib.suppress(Exception):
                    transport.close()
                return True, None, latency_ms, None

        ok, err, latency_ms, err_no = await hass.async_add_executor_job(_probe)
        self._record_status(ok, err, latency_ms, err_no)

    def _record_status(
        self,
        ok: bool,
        err: str | None,
        latency_ms: int | None,
        err_no: int | None,
    ) -> None:
        """Update status bookkeeping fields and notify listeners."""
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
            self._last_error_errno = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(
                err or "Serial printer unreachable"
            )
            self._last_error_errno = err_no
        if self._status != ok and not ok:
            _LOGGER.warning(
                "Serial printer %s not reachable",
                sanitize_log_message(self._serial_config.serial_port),
            )
        self._notify_status_change(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        port = self._serial_config.serial_port
        baudrate = self._serial_config.baudrate
        if _is_url(port):
            return f"Serial {sanitize_log_message(port)}"
        return f"Serial {sanitize_log_message(port)}@{baudrate}bps"

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Start the adapter (serial ignores keepalive, like USB/Bluetooth)."""
        await super().start(hass, keepalive=False, status_interval=status_interval)
