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
                transport = serial_transport.open_serial_transport(
                    port,
                    baudrate,
                    timeout,
                    write_chunk_size=self._serial_config.write_chunk_size,
                    write_chunk_delay_ms=self._serial_config.write_chunk_delay_ms,
                )
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

    async def _release_printer(
        self, hass: HomeAssistant, printer: Any, *, owned: bool, failed: bool = False
    ) -> None:
        """Flush coalesced output (errors propagate) before the base close.

        The serial transport buffers every ``_raw()`` micro-write and only
        sends the payload to the wire when the connection is flushed/closed.
        The base ``_release_printer`` closes best-effort (suppressing
        exceptions), so without this a write that fails at flush time —
        device unplugged, ESPHome proxy reset, socket dropped mid-flush —
        would be swallowed and the operation reported as success. On the
        success path (``owned`` reconnect-per-op, ``not failed``) we flush
        explicitly here: a failed write raises out of the operation's
        ``finally``, skipping ``_mark_success`` so the caller sees the
        error. The connection is still closed afterwards either way.
        """
        flush_exc: Exception | None = None
        if owned and not failed and printer is not None:

            def _flush() -> None:
                printer.flush()

            try:
                await hass.async_add_executor_job(_flush)
            except Exception as exc:  # surfaced after the close below
                flush_exc = exc
                failed = True

        await super()._release_printer(hass, printer, owned=owned, failed=failed)
        if flush_exc is not None:
            raise flush_exc

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Check serial printer reachability.

        For filesystem paths we do a non-invasive character-device check
        (``os.stat`` + ``stat.S_ISCHR``). For URL-based connections (ESPHome
        proxy, RFC2217, socket) we attempt a brief open/close, since there is
        no device-file to inspect.

        The probe runs under the operation lock via ``_probe_lock_or_skip``
        so it cannot race a print onto the same transport: a bare
        ``if self._lock.locked(): return`` was TOCTOU — a print could acquire
        the lock between the check and the probe, leaving a status open/close
        to a URL proxy (ESPHome/socket/RFC2217) running concurrently with the
        active job. When a print already holds the lock, this tick is skipped.
        """
        port = self._serial_config.serial_port

        async with self._probe_lock_or_skip() as acquired:
            if not acquired:
                _LOGGER.debug(
                    "Skipping serial status probe for %s — print operation in flight",
                    sanitize_log_message(port),
                )
                return
            probe = self._probe_url if _is_url(port) else self._probe_path
            ok, err, latency_ms, err_no = await hass.async_add_executor_job(probe, port)

        self._record_status(ok, err, latency_ms, err_no)

    def _probe_path(self, port: str) -> tuple[bool, str | None, int | None, int | None]:
        """Non-invasive reachability probe for filesystem serial ports."""
        start = time.perf_counter()
        try:
            st = os.stat(port)
        except OSError as exc:
            latency_ms = int((time.perf_counter() - start) * 1000)
            return False, str(exc), latency_ms, getattr(exc, "errno", None)
        latency_ms = int((time.perf_counter() - start) * 1000)
        if not stat.S_ISCHR(st.st_mode):
            return False, f"{port} is not a character device", latency_ms, None
        return True, None, latency_ms, None

    def _probe_url(self, port: str) -> tuple[bool, str | None, int | None, int | None]:
        """Reachability probe for URL serial ports via a brief open/close."""
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
        latency_ms = int((time.perf_counter() - start) * 1000)
        with contextlib.suppress(Exception):
            transport.close()
        return True, None, latency_ms, None

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
