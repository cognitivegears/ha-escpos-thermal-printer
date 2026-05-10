"""Bluetooth Classic / RFCOMM printer adapter implementation."""

from __future__ import annotations

import contextlib
import errno
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import sanitize_log_message
from . import bluetooth_transport
from ._escpos_bluetooth import make_bluetooth_escpos
from .base_adapter import EscposPrinterAdapterBase
from .config import BluetoothPrinterConfig

_LOGGER = logging.getLogger(__name__)


# Errnos that indicate genuinely transient RFCOMM failures worth retrying:
# EBUSY (16) — link held by another connection that may release imminently
# EIO (5)   — kernel hiccup on a freshly-woken radio
#
# We deliberately do NOT retry ETIMEDOUT or EHOSTDOWN: a printer that didn't
# answer in `timeout` seconds isn't going to answer in another `timeout`
# seconds either, and at three attempts x default 4 s timeout we'd block
# the executor pool for 12+ s per print attempt. The user re-issuing the
# print is a much cheaper recovery than amplifying executor pressure.
_RETRYABLE_ERRNOS = {errno.EBUSY, errno.EIO}


class BluetoothPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for Bluetooth Classic / RFCOMM ESC/POS printers."""

    _CONNECT_RETRIES = 2
    _CONNECT_RETRY_DELAY_S = 0.3

    def __init__(self, config: BluetoothPrinterConfig) -> None:
        super().__init__(config)
        self._bt_config = config
        # MAC is immutable for the adapter's lifetime; cache the redacted form
        # so log calls don't pay the regex cost on every print/status tick.
        self._mac_redacted = sanitize_log_message(config.mac)
        # Bluetooth printers behave like USB: one client at a time, the link
        # can drop on idle. Force connect-per-operation.
        self._keepalive = False

    @property
    def config(self) -> BluetoothPrinterConfig:
        """Return the Bluetooth printer configuration."""
        return self._bt_config

    def _connect(self) -> Any:
        """Open an RFCOMM transport and wrap it in a python-escpos printer."""
        profile_obj = self._get_profile_obj()
        last_exc: Exception | None = None
        for attempt in range(self._CONNECT_RETRIES + 1):
            try:
                transport = bluetooth_transport.open_rfcomm_transport(
                    self._bt_config.mac,
                    self._bt_config.rfcomm_channel,
                    self._bt_config.timeout,
                )
            except Exception as exc:
                last_exc = exc
                err_no = getattr(exc, "errno", None)
                self._last_error_errno = err_no
                _LOGGER.debug(
                    "Bluetooth open failed for %s ch=%s (attempt %s/%s errno=%s): %s",
                    self._mac_redacted,
                    self._bt_config.rfcomm_channel,
                    attempt + 1,
                    self._CONNECT_RETRIES + 1,
                    err_no,
                    sanitize_log_message(str(exc)),
                )
                retryable = err_no in _RETRYABLE_ERRNOS if err_no is not None else False
                if attempt >= self._CONNECT_RETRIES or not retryable:
                    _LOGGER.warning(
                        "Bluetooth open failed for %s ch=%s (errno=%s): %s",
                        self._mac_redacted,
                        self._bt_config.rfcomm_channel,
                        err_no,
                        sanitize_log_message(str(exc)),
                    )
                    raise
                time.sleep(self._CONNECT_RETRY_DELAY_S)
                continue
            else:
                return make_bluetooth_escpos(transport, profile_obj)
        # Loop only exits via return or re-raise above. This line is
        # defensive: if a future refactor changes a `raise` to `break`,
        # the assert fails loudly instead of silently passing `None` to
        # `raise`.
        assert last_exc is not None  # pragma: no cover
        raise last_exc

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Check Bluetooth printer reachability via a short RFCOMM probe.

        We don't talk to bluez D-Bus here — a paired-but-asleep printer is
        often only revealed by attempting an actual RFCOMM connect. The
        probe immediately closes the link to avoid blocking real prints.

        RFCOMM accepts only one client at a time, so a status probe issued
        during an in-flight print would race for the printer's only slot:
        the probe could see ``EBUSY`` (false-negative offline status) or,
        worse, kick the active print on poorly-behaving printer firmware.
        We skip the tick if a print operation currently holds the lock and
        let the next print/tick refresh status.
        """
        if self._lock.locked():
            _LOGGER.debug(
                "Skipping Bluetooth status probe for %s ch=%s — "
                "print operation in flight",
                self._mac_redacted,
                self._bt_config.rfcomm_channel,
            )
            return

        def _probe() -> tuple[bool, str | None, int | None, int | None]:
            start = time.perf_counter()
            try:
                transport = bluetooth_transport.open_rfcomm_transport(
                    self._bt_config.mac,
                    self._bt_config.rfcomm_channel,
                    min(self._bt_config.timeout, 3.0),
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
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
            self._last_error_errno = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "Bluetooth printer unreachable")
            self._last_error_errno = err_no
        if self._status != ok and not ok:
            _LOGGER.warning(
                "Bluetooth printer %s ch=%s not reachable",
                self._mac_redacted,
                self._bt_config.rfcomm_channel,
            )
        self._notify_status_change(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        return f"BT {self._bt_config.mac} ch={self._bt_config.rfcomm_channel}"

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Start the adapter (Bluetooth ignores keepalive, like USB)."""
        await super().start(hass, keepalive=False, status_interval=status_interval)
