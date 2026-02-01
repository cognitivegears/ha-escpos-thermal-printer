"""USB printer adapter implementation."""

from __future__ import annotations

import contextlib
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import sanitize_log_message
from .base_adapter import EscposPrinterAdapterBase, _get_usb_printer
from .config import UsbPrinterConfig

_LOGGER = logging.getLogger(__name__)


class UsbPrinterAdapter(EscposPrinterAdapterBase):
    """Adapter for USB ESC/POS printers."""

    _CONNECT_RETRIES = 2
    _CONNECT_RETRY_DELAY_S = 0.3

    def __init__(self, config: UsbPrinterConfig) -> None:
        super().__init__(config)
        self._usb_config = config
        # USB printers don't support keepalive - reconnect per operation
        self._keepalive = False

    @property
    def config(self) -> UsbPrinterConfig:
        """Return the USB printer configuration."""
        return self._usb_config

    def _connect(self) -> Any:
        """Create and return a USB printer connection."""
        usb_class = _get_usb_printer()
        profile_obj = self._get_profile_obj()
        def _is_retryable(exc: Exception) -> bool:
            try:
                import usb.core  # noqa: PLC0415

                if isinstance(exc, usb.core.USBError):
                    return exc.errno in {5, 16, 19}  # EIO, EBUSY, ENODEV
            except Exception:
                # usb library not available or unexpected error; fall back to string-based matching below
                pass
            err = str(exc).lower()
            return any(token in err for token in ("input/output error", "resource busy", "no device"))

        def _get_kernel_driver_active() -> bool | None:
            try:
                import usb.core  # noqa: PLC0415

                device = usb.core.find(
                    idVendor=self._usb_config.vendor_id,
                    idProduct=self._usb_config.product_id,
                )
                if device is None or not hasattr(device, "is_kernel_driver_active"):
                    return None
                try:
                    return bool(device.is_kernel_driver_active(0))
                except Exception:
                    return None
            except Exception:
                return None

        last_exc: Exception | None = None
        for attempt in range(self._CONNECT_RETRIES + 1):
            try:
                return usb_class(
                    self._usb_config.vendor_id,
                    self._usb_config.product_id,
                    timeout=int(self._usb_config.timeout * 1000),  # USB timeout in milliseconds
                    in_ep=self._usb_config.in_ep,
                    out_ep=self._usb_config.out_ep,
                    profile=profile_obj,
                )
            except Exception as exc:
                last_exc = exc
                kernel_driver_active = _get_kernel_driver_active()
                errno = getattr(exc, "errno", None)
                self._last_error_errno = errno
                _LOGGER.debug(
                    "USB open failed for %04X:%04X (attempt %s/%s errno=%s kernel_driver_active=%s): %s",
                    self._usb_config.vendor_id,
                    self._usb_config.product_id,
                    attempt + 1,
                    self._CONNECT_RETRIES + 1,
                    errno,
                    kernel_driver_active,
                    sanitize_log_message(str(exc)),
                )
                if attempt >= self._CONNECT_RETRIES or not _is_retryable(exc):
                    _LOGGER.warning(
                        "USB open failed for %04X:%04X (errno=%s kernel_driver_active=%s): %s",
                        self._usb_config.vendor_id,
                        self._usb_config.product_id,
                        errno,
                        kernel_driver_active,
                        sanitize_log_message(str(exc)),
                    )
                    raise
                time.sleep(self._CONNECT_RETRY_DELAY_S)
        raise last_exc  # pragma: no cover

    async def _status_check(self, hass: HomeAssistant) -> None:
        """Check USB device availability via device enumeration."""
        def _probe() -> tuple[bool, str | None, int | None]:
            start = time.perf_counter()
            try:
                import usb.core  # noqa: PLC0415

                device = usb.core.find(
                    idVendor=self._usb_config.vendor_id,
                    idProduct=self._usb_config.product_id,
                )
                latency_ms = int((time.perf_counter() - start) * 1000)
            except Exception as e:
                latency_ms = int((time.perf_counter() - start) * 1000)
                return False, str(e), latency_ms
            else:
                if device is not None:
                    return True, None, latency_ms
                return False, "USB device not found", latency_ms

        ok, err, latency_ms = await hass.async_add_executor_job(_probe)
        now = dt_util.utcnow()
        self._last_check = now
        self._last_latency_ms = latency_ms
        if ok:
            self._last_ok = now
            self._last_error_reason = None
            self._last_error_errno = None
        else:
            self._last_error = now
            self._last_error_reason = sanitize_log_message(err or "USB device unavailable")
        if self._status != ok:
            self._status = ok
            if not ok:
                _LOGGER.warning(
                    "USB Printer %04X:%04X not available",
                    self._usb_config.vendor_id,
                    self._usb_config.product_id,
                )
            # Notify listeners
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""
        return f"USB {self._usb_config.vendor_id:04X}:{self._usb_config.product_id:04X}"

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Start the adapter (USB ignores keepalive)."""
        # USB doesn't support persistent connections, override keepalive to False
        await super().start(hass, keepalive=False, status_interval=status_interval)
