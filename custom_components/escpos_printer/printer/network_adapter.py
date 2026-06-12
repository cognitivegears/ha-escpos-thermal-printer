"""Network (TCP/IP) printer adapter implementation."""

from __future__ import annotations

import contextlib
import logging
import socket
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import sanitize_log_message
from .base_adapter import EscposPrinterAdapterBase, _get_network_printer
from .config import NetworkPrinterConfig

_LOGGER = logging.getLogger(__name__)


class NetworkPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for network (TCP/IP) ESC/POS printers."""

    def __init__(self, config: NetworkPrinterConfig) -> None:
        super().__init__(config)
        self._network_config = config

    @property
    def config(self) -> NetworkPrinterConfig:
        """Return the network printer configuration."""
        return self._network_config

    def _connect(self) -> Any:
        """Create and return a network printer connection."""
        network_class = _get_network_printer()
        return network_class(
            self._network_config.host,
            port=self._network_config.port,
            timeout=self._network_config.timeout,
            profile=self._profile_for_constructor(),
        )

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Non-invasive TCP reachability check for network printers.

        P-M2: skip the probe entirely if a print is in flight. Opening a
        second TCP connection to the same printer mid-print can flap
        bandwidth-constrained transports (Bluetooth/USB-IP via TCP
        gateway). The status sensor stays at its last-known value
        until the print completes — strictly better than corrupting an
        active job.
        """

        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            try:
                with socket.create_connection(
                    (self._network_config.host, self._network_config.port),
                    timeout=min(self._network_config.timeout, 3.0),
                ):
                    latency_ms = int((time.perf_counter() - start) * 1000)
                    return True, None, latency_ms
            except OSError as e:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return False, str(e), latency_ms

        async with self._probe_lock_or_skip() as acquired:
            if not acquired:
                _LOGGER.debug("Skipping network status probe; print in flight")
                return
            ok, err, latency_ms = await hass.async_add_executor_job(_probe)
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "unreachable")
        if self._status != ok:
            self._status = ok
            if not ok:
                _LOGGER.warning(
                    "Printer %s:%s not reachable",
                    self._network_config.host,
                    self._network_config.port,
                )
            # Notify listeners
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        return f"{self._network_config.host}:{self._network_config.port}"
