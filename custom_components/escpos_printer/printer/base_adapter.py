"""Base adapter class for ESC/POS printers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import asyncio
from collections.abc import AsyncIterator, Callable
import contextlib
import logging
import textwrap
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from ..security import (
    MAX_FEED_LINES,
    sanitize_log_message,
    validate_numeric_input,
    validate_timeout,
)
from .barcode_operations import BarcodeOperationsMixin
from .config import BasePrinterConfig
from .control_operations import ControlOperationsMixin
from .image_operations import (
    ImageOperationsMixin,
    ImageStats,
    _print_prepared_under_lock,
    prepare_image_for_print,
    profile_width_bypass,
)
from .image_processor import FALLBACK_PROFILE_WIDTH
from .mapping_utils import cleanup_cut, map_align, map_cut, map_multiplier, map_underline
from .print_operations import PrintOperationsMixin, _print_text_under_lock, _qr_under_lock

if TYPE_CHECKING:
    from homeassistant.core import Context

_LOGGER = logging.getLogger(__name__)


# Late import of python-escpos to avoid import errors at HA startup if deps pending
def _get_network_printer() -> type[Any]:
    from escpos.printer import Network  # noqa: PLC0415

    return Network  # type: ignore[no-any-return]


def _get_usb_printer() -> type[Any]:
    from escpos.printer import Usb  # noqa: PLC0415

    return Usb  # type: ignore[no-any-return]


def profile_width_issue_id(entry_id: str | None) -> str:
    """Build the per-entry repair-issue id for the profile-width fallback.

    Scoped by ``entry_id`` (rather than profile name) so two entries
    configured with the same profile don't share — and clobber — the same
    issue. Also used by ``async_remove_entry`` to clean up on entry
    removal.
    """
    return f"profile_width_fallback_{entry_id or 'unknown'}"


class EscposPrinterAdapterBase(
    PrintOperationsMixin,
    ImageOperationsMixin,
    BarcodeOperationsMixin,
    ControlOperationsMixin,
    ABC,
):
    """Abstract base class for ESC/POS printer adapters."""

    # Per-transport default for the inter-slice delay in
    # ``print_image``. 0 ms is fine for fast transports (TCP/USB);
    # Bluetooth-SPP needs ~50 ms to drain its buffer between writes.
    # Subclasses override.
    default_chunk_delay_ms: ClassVar[int] = 0

    # Per-printer reliability profile overrides — populated by
    # ``async_setup_entry`` from the options flow. Keys may include
    # ``fragment_height``, ``chunk_delay_ms``, ``impl``. Empty dict
    # means "transport defaults".
    reliability_profile_defaults: dict[str, Any]

    def __init__(self, config: BasePrinterConfig) -> None:
        self._config: BasePrinterConfig = config
        # Validate timeout eagerly
        self._config.timeout = validate_timeout(self._config.timeout)
        # Set by async_setup_entry after construction; used to scope repair
        # issues (e.g. profile_width_fallback) to this entry so two entries
        # sharing a profile name don't clobber each other's issue.
        self.entry_id: str | None = None
        self._keepalive: bool = False
        self._status_interval: int = 0
        self._printer: Any = None
        self._lock = asyncio.Lock()
        self._cancel_status: Callable[[], None] | None = None
        self._status: bool | None = None
        self._status_listeners: list[Callable[[bool], None]] = []
        self._last_check: Any = None
        self._last_ok: Any = None
        self._last_error: Any = None
        self._last_latency_ms: int | None = None
        self._last_paper_status: int | None = None
        self._last_error_reason: str | None = None
        self._last_error_errno: int | None = None
        self._cached_profile_width: int | None = None
        self._profile_width_lookup_done: bool = False
        self._profile_width_warning_logged = False
        # Image-pipeline diagnostics counters / snapshot fields. Updated
        # by ImageOperationsMixin and surfaced via get_diagnostics().
        self._image_stats: ImageStats = ImageStats()
        # Per-printer reliability profile defaults, populated by
        # ``async_setup_entry``. Empty dict means "use transport defaults".
        self.reliability_profile_defaults = {}
        # Per-entry default image implementation, resolved at setup from
        # CONF_IMPL / pick_impl(profile). None -> DEFAULT_IMPL at use time.
        self.default_impl: str | None = None
        # True when the profile explicitly declares no image support;
        # prepare_image warns once but still prints (hints, not gates).
        self.profile_no_image_support: bool = False
        self._no_image_warned: bool = False

    @property
    def config(self) -> BasePrinterConfig:
        """Return the printer configuration."""
        return self._config

    @property
    def allow_local_image_urls(self) -> bool:
        """Whether image URLs may resolve to private/LAN/loopback addresses."""
        return self._config.allow_local_image_urls

    @abstractmethod
    def _connect(self) -> Any:
        """Create and return a printer connection."""

    @abstractmethod
    async def _status_check(self, hass: HomeAssistant) -> None:
        """Perform a status check for the printer."""

    @abstractmethod
    def get_connection_info(self) -> str:
        """Return a human-readable connection info string."""

    async def start(self, hass: HomeAssistant, *, keepalive: bool, status_interval: int) -> None:
        """Start the adapter with optional keepalive and status checking."""
        self._keepalive = bool(keepalive)
        self._status_interval = max(0, int(status_interval))

        # Establish initial connection if keeping alive
        if self._keepalive and self._printer is None:

            def _mk() -> Any:
                return self._connect()

            self._printer = await hass.async_add_executor_job(_mk)

        # Schedule status checks
        if self._status_interval > 0:
            from datetime import timedelta  # noqa: PLC0415

            from homeassistant.helpers.event import async_track_time_interval  # noqa: PLC0415

            async def _tick(now: Any) -> None:
                await self._status_check(hass)

            self._cancel_status = async_track_time_interval(
                hass, _tick, timedelta(seconds=self._status_interval)
            )
        # Always run a one-shot initial probe, regardless of whether the
        # recurring timer above is enabled. Without this, entities that
        # read get_status() at construction (e.g. the connectivity
        # binary_sensor) see None ("unknown") until the first print
        # succeeds or fails -- status_interval defaults to 0, so most
        # installs never get a periodic probe at all. Errors are swallowed
        # here (not just inside _status_check's own transport-specific
        # try/except) so a probe failure never fails entry setup.
        try:
            await self._status_check(hass)
        except Exception as err:  # pragma: no cover - defensive
            _LOGGER.debug("Initial status probe failed: %s", sanitize_log_message(str(err)))

    async def stop(self, hass: HomeAssistant | None = None) -> None:
        """Stop the adapter and clean up resources.

        Acquires the operation lock so an in-flight keepalive print isn't
        torn out from under the executor thread writing to the socket,
        and closes the connection on an executor thread (``close()`` does
        a blocking ``socket.shutdown``) rather than on the event loop.
        """
        if self._cancel_status:
            self._cancel_status()
        self._cancel_status = None

        async with self._lock:
            printer = self._printer
            self._printer = None
            if printer is None:
                return

            def _close() -> None:
                with contextlib.suppress(Exception):
                    printer.close()

            if hass is not None:
                await hass.async_add_executor_job(_close)
            else:
                # No hass available (rare teardown path): close inline as
                # a last resort rather than leaking the socket.
                _close()

    @contextlib.asynccontextmanager
    async def _probe_lock_or_skip(self) -> AsyncIterator[bool]:
        """Hold the op lock for a status probe, or yield ``False`` if busy.

        A status probe must be mutually exclusive with a print on the
        same transport (opening a second connection mid-print can flap
        bandwidth-constrained links or, on USB/BT, disturb the active
        job). ``if self._lock.locked(): return`` followed by awaiting
        the probe was TOCTOU — a print could acquire the lock between the
        check and the probe. Acquiring the lock makes check-and-hold
        atomic: when the lock is free, asyncio's ``Lock.acquire``
        completes without suspending, so nothing can interleave between
        the ``locked()`` test and the acquisition.

        Note the contention now runs both ways: a print arriving while a
        probe is mid-flight blocks on the lock until the probe finishes
        (bounded by the probe's ``min(timeout, 3.0)`` ceiling). This is
        the intended correctness-over-latency trade-off.
        """
        if self._lock.locked():
            yield False
            return
        await self._lock.acquire()
        try:
            yield True
        finally:
            self._lock.release()

    def get_status(self) -> bool | None:
        """Return the current printer status."""
        return self._status

    async def async_request_status_check(self, hass: HomeAssistant) -> None:
        """Request an immediate status check."""
        await self._status_check(hass)

    async def get_paper_status(self, hass: HomeAssistant) -> int | None:
        """Query the paper sensor via DLE EOT (2=ok, 1=low, 0=out).

        Returns ``None`` when the status is unknown (printer unreachable
        or the query failed). Only meaningful on transports with a real
        read channel (network, USB): the Bluetooth/serial escpos
        subclasses stub ``_read()`` to ``b""``, which python-escpos
        misreports as "plenty of paper" — so those entries never create
        the paper sensor.

        If a print is in flight, returns the last known value instead of
        contending for the transport.
        """
        async with self._probe_lock_or_skip() as acquired:
            if not acquired:
                _LOGGER.debug("Skipping paper status query; print in flight")
                return self._last_paper_status
            printer: Any = None
            owned = False
            failed = True
            try:
                printer, owned = await self._acquire_printer_or_offline(hass)
                # Reaching the printer at all is the reachability signal --
                # notify here, not after the DLE EOT query below, so a
                # printer that ignores/times out on paper-status (a real,
                # known category -- see the docstring) stays stably Online
                # instead of flapping every 5-minute poll (SCAN_INTERVAL
                # in sensor.py) on that query alone.
                await self._mark_success()
                status = await hass.async_add_executor_job(printer.paper_status)
                failed = False
            except Exception as e:
                # Connect failures already went through
                # `_acquire_printer_or_offline`, which set `_last_check` /
                # `_last_error` / `_last_error_reason` and notified offline
                # (a no-op here if already offline, via `_notify_status_change`'s
                # dedup) -- no bespoke bookkeeping needed for that case.
                _LOGGER.debug("Paper status query failed: %s", sanitize_log_message(str(e)))
                self._last_paper_status = None
                return None
            finally:
                if printer is not None:
                    # notify_status=False: a query-level failure here does
                    # NOT flip back to offline -- we already proved
                    # reachability above by connecting successfully.
                    await self._release_printer(
                        hass, printer, owned=owned, failed=failed, notify_status=False
                    )
            self._last_paper_status = int(status)
            return self._last_paper_status

    def add_status_listener(self, callback: Callable[[bool], None]) -> Callable[[], None]:
        """Add a status change listener and return an unsubscribe function."""
        self._status_listeners.append(callback)

        def _remove() -> None:
            with contextlib.suppress(ValueError):
                self._status_listeners.remove(callback)

        return _remove

    def get_diagnostics(self) -> dict[str, Any]:
        """Return diagnostic information about the adapter."""

        def _iso(dt_obj: Any) -> str | None:
            return dt_obj.isoformat() if dt_obj is not None else None

        return {
            "last_check": _iso(self._last_check),
            "last_ok": _iso(self._last_ok),
            "last_error": _iso(self._last_error),
            "last_latency_ms": self._last_latency_ms,
            "paper_status": self._last_paper_status,
            "last_error_reason": self._last_error_reason,
            "last_error_errno": self._last_error_errno,
            "default_chunk_delay_ms": self.default_chunk_delay_ms,
            "profile_width": self._cached_profile_width,
            "reliability_profile_defaults": dict(self.reliability_profile_defaults),
            "image_pipeline": self._image_stats.as_dict(),
        }

    async def _acquire_printer(self, hass: HomeAssistant) -> tuple[Any, bool]:
        """Return a printer instance and whether it should be closed by the caller."""
        if self._keepalive and self._printer is not None:
            return self._printer, False
        printer = await hass.async_add_executor_job(self._connect)
        return printer, True

    async def _acquire_printer_or_offline(self, hass: HomeAssistant) -> tuple[Any, bool]:
        """``_acquire_printer``, marking the adapter offline on connect failure.

        Every operation acquires its printer *before* entering the
        try/finally that calls ``_release_printer`` on failure -- so a
        ``_connect()`` exception used to skip the offline notification
        entirely and the connectivity sensor stayed latched "Online".
        Wrapping the acquire here gives every call site the same offline
        signal a failed operation already gets via ``_release_printer``.
        """
        try:
            return await self._acquire_printer(hass)
        except Exception:
            now = dt_util.utcnow()
            self._last_check = now
            self._last_error = now
            self._last_error_reason = "connect failed"
            self._notify_status_change(False)
            raise

    async def _release_printer(
        self,
        hass: HomeAssistant,
        printer: Any,
        *,
        owned: bool,
        failed: bool = False,
        notify_status: bool = True,
    ) -> None:
        """Release a printer instance after an operation.

        Caller-owned connections (the reconnect-per-operation model) are
        always closed. A persistent keepalive connection is kept open on
        success, but **invalidated on failure**: a broken pipe / idle
        timeout / power-cycle leaves the socket dead, and reusing it
        would brick every subsequent print until the entry is reloaded.
        Dropping it here forces the next ``_acquire_printer`` to
        reconnect. Runs under the operation lock, so nulling
        ``self._printer`` is race-free.

        A failed operation is also an offline signal in its own right —
        with status polling disabled by default (``status_interval=0``),
        operation outcomes are the only thing that ever updates the
        connectivity sensor. Without this, a run of failed prints leaves
        the "Online" sensor latched on indefinitely.

        ``notify_status=False`` opts a caller out of that offline signal
        for failures that don't indicate the transport is down — pass
        ``failed=True`` for the keepalive-invalidation behaviour above
        without flapping the connectivity sensor.
        """
        if owned:

            def _close() -> None:
                with contextlib.suppress(Exception):
                    printer.close()

            await hass.async_add_executor_job(_close)
        elif failed and self._printer is not None:
            stale = self._printer
            self._printer = None

            def _close_stale() -> None:
                with contextlib.suppress(Exception):
                    stale.close()

            await hass.async_add_executor_job(_close_stale)

        if failed and notify_status:
            now = dt_util.utcnow()
            self._last_check = now
            self._last_error = now
            self._last_error_reason = "print operation failed"
            self._notify_status_change(False)

    def _notify_status_change(self, ok: bool) -> None:
        """Notify all status listeners of a status change."""
        if self._status != ok:
            self._status = ok
            for cb in list(self._status_listeners):
                with contextlib.suppress(Exception):
                    cb(ok)

    def _wrap_text(self, text: str) -> str:
        """Wrap text to the configured line width."""
        cols = max(0, int(self._config.line_width or 0))
        if cols <= 0:
            return text
        wrapped_lines: list[str] = []
        for line in text.splitlines():
            # Preserve empty lines
            if not line:
                wrapped_lines.append("")
                continue
            wrapped_lines.extend(
                textwrap.wrap(line, width=cols, replace_whitespace=False, drop_whitespace=False)
            )
        # splitlines() drops the final line terminator; restore it. A
        # trailing \n is load-bearing for callers that print with feed=0
        # (calibration labels) — without it the last line sits unflushed
        # in the printer's line buffer and the next image/raw command
        # drops or merges it (seen on Ronga RP850P).
        suffix = "\n" if text.endswith("\n") else ""
        return "\n".join(wrapped_lines) + suffix

    # Static methods delegated to mapping_utils for backward compatibility
    @staticmethod
    def _map_align(align: str | None) -> str:
        """Map alignment string to escpos alignment value."""
        return map_align(align)

    @staticmethod
    def _map_underline(underline: str | None) -> int:
        """Map underline string to escpos underline value."""
        return map_underline(underline)

    @staticmethod
    def _map_multiplier(val: str | None) -> int:
        """Map multiplier string to escpos multiplier value."""
        return map_multiplier(val)

    @staticmethod
    def _map_cut(mode: str | None) -> str | None:
        """Map cut mode string to escpos cut value."""
        return map_cut(mode)

    def _get_profile_obj(self) -> Any:
        """Get the escpos profile object for this configuration."""
        if self._config.profile:
            try:
                # python-escpos 3.x exposes ``get_profile`` from
                # ``escpos.capabilities`` (the old ``escpos.profile``
                # module was removed; importing it silently returned
                # None, so the configured profile was never applied at
                # connect time).
                from escpos.capabilities import get_profile  # noqa: PLC0415

                return get_profile(self._config.profile)
            except Exception as e:
                _LOGGER.debug(
                    "Unknown printer profile '%s': %s",
                    self._config.profile,
                    sanitize_log_message(str(e)),
                )
        return None

    def _profile_for_constructor(self) -> str | None:
        """Profile kwarg for python-escpos printer constructors.

        Must be the profile *name*, not the resolved object:
        ``Escpos.__init__`` runs the kwarg through
        ``capabilities.get_profile()``, whose isinstance fast-path only
        accepts instances of the library's *default* profile class. A
        specific profile instance (e.g. ``TMT20IIProfile``) falls through
        to a dict lookup keyed by the object itself, so every connect
        dies with ``KeyError: <...TMT20IIProfile object...>``. Validating
        via :meth:`_get_profile_obj` first keeps the old behaviour for
        unknown profiles — degrade to the library default with a debug
        log instead of raising at connect time.
        """
        if self._get_profile_obj() is not None:
            return self._config.profile
        return None

    def get_profile_pixel_width(self, hass: HomeAssistant | None = None) -> int | None:
        """Return the printer profile's max pixel width (cached).

        Resolved from the configured python-escpos profile object — not
        from the live connection, which is ``None`` for USB, Bluetooth,
        and non-keepalive network printers (i.e. nearly every install),
        so reading it there always missed.

        When a profile *is* configured but exposes no pixel width, falls
        back to :data:`FALLBACK_PROFILE_WIDTH`, logs a single WARNING per
        adapter instance, and (when ``hass`` is provided) raises a
        repairs issue so the miss is visible in the UI — silently
        miscalibrated images are the resulting #1 support question. The
        auto/default profile (no profile chosen) has no declared pixel
        width by design, so it falls back silently without warning.
        """
        override = getattr(self._config, "width_pixels", None)
        if override:
            # User-set width beats the profile and retires any open
            # profile_width_fallback repairs issue for this entry.
            if hass is not None:
                self._clear_profile_width_repair_issue(hass)
            return int(override)
        if self._profile_width_lookup_done:
            return self._cached_profile_width
        width: int | None = None
        profile_obj = self._get_profile_obj()
        if profile_obj is not None:
            try:
                data = profile_obj.profile_data["media"]["width"]["pixels"]
                if isinstance(data, (int, float)):
                    width = int(data)
            except AttributeError, KeyError, TypeError, ValueError:
                width = None
        self._cached_profile_width = width
        self._profile_width_lookup_done = True
        # Only surface the fallback when the user actually picked a
        # profile that turned out to lack width data; auto/default
        # (``profile_obj is None``) is an expected, silent fallback.
        fallback_applies = width is None and profile_obj is not None
        if fallback_applies:
            if not self._profile_width_warning_logged:
                _LOGGER.warning(
                    "Printer profile '%s' does not expose media.width.pixels; "
                    "falling back to %dpx for image width. Set image_width "
                    "explicitly or pick a profile that declares a pixel width.",
                    self._config.profile,
                    FALLBACK_PROFILE_WIDTH,
                )
                self._profile_width_warning_logged = True
            if hass is not None:
                self._raise_profile_width_repair_issue(hass)
        elif hass is not None:
            # The profile now resolves fine (or auto/default no longer
            # needs one) -- clear any fallback issue filed for this entry
            # by a previous, now-fixed profile choice.
            self._clear_profile_width_repair_issue(hass)
        return width

    def _raise_profile_width_repair_issue(self, hass: HomeAssistant) -> None:
        """File a repair issue so the user sees the fallback in the UI."""
        try:
            from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

            from ..const import DOMAIN  # noqa: PLC0415
        except ImportError:
            return
        profile_name = getattr(self._config, "profile", None) or "default"
        try:
            ir.async_create_issue(
                hass,
                DOMAIN,
                profile_width_issue_id(self.entry_id),
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="profile_width_fallback",
                translation_placeholders={
                    "profile": profile_name,
                    "fallback": str(FALLBACK_PROFILE_WIDTH),
                },
            )
        except Exception as exc:
            _LOGGER.debug("Could not create profile_width repair issue: %s", exc)

    def _clear_profile_width_repair_issue(self, hass: HomeAssistant) -> None:
        """Delete this entry's fallback issue once the profile resolves."""
        try:
            from homeassistant.helpers import issue_registry as ir  # noqa: PLC0415

            from ..const import DOMAIN  # noqa: PLC0415
        except ImportError:
            return
        try:
            ir.async_delete_issue(hass, DOMAIN, profile_width_issue_id(self.entry_id))
            # Pre-1.0 issue ids were scoped by profile name; delete the
            # legacy id too so issues created before the entry_id scoping
            # don't orphan forever.
            if self.config.profile:
                ir.async_delete_issue(hass, DOMAIN, f"profile_width_fallback_{self.config.profile}")
        except Exception as exc:
            _LOGGER.debug("Could not delete profile_width repair issue: %s", exc)

    async def _apply_cut_and_feed(
        self, hass: HomeAssistant, printer: Any, cut: str | None, feed: int | None
    ) -> None:
        """Apply feed and cut operations to the printer.

        ``feed=None`` means "no explicit feed" (no lines emitted).
        ``feed=0`` is equivalent. Adapters treat the two interchangeably.
        """
        # feed first, then cut
        if feed is not None:
            lines = validate_numeric_input(feed, 0, MAX_FEED_LINES, "feed")
            if lines > 0:

                def _feed() -> None:
                    # Some versions have ln(); otherwise send newlines
                    if hasattr(printer, "ln"):
                        printer.ln(lines)
                    else:
                        try:
                            printer._raw(b"\n" * lines)
                        except Exception:
                            for _ in range(lines):
                                printer.text("\n")

                await hass.async_add_executor_job(_feed)

        cut_mode = self._map_cut(cut)
        if cut_mode:

            def _cut() -> None:
                try:
                    printer.cut(mode=cut_mode)
                except Exception as e:
                    _LOGGER.debug("Cut not supported: %s", e)

            await hass.async_add_executor_job(_cut)

    async def _mark_success(self) -> None:
        """Mark a successful operation (updates status tracking).

        Routed through ``_notify_status_change`` (rather than firing
        listeners directly) so a success that doesn't change the status
        -- e.g. the 5-minute paper-status poll on an already-online
        printer -- doesn't re-fire every listener with a no-op update.
        """
        now = dt_util.utcnow()
        self._last_ok = now
        self._last_check = now
        self._last_error_errno = None
        self._notify_status_change(True)

    @contextlib.asynccontextmanager
    async def batch_connection(self, hass: HomeAssistant) -> AsyncIterator[_BatchPage]:
        """Run several prints over one lock acquisition and one connection.

        The reconnect-per-operation model sends each print on its own
        short-lived connection. Printer interfaces that accept the next
        connection before the previous one's buffer has drained can
        reorder or interleave the fragments on paper (observed on a
        TM-T20II ethernet interface during calibration: labels printed
        out of order and one raster row garbled mid-stream). Any page
        that must render in order belongs on a single connection.

        Yields a :class:`_BatchPage` bound to the held connection. An
        exception escaping the ``with`` body releases the connection
        with ``failed=True`` (offline signal + keepalive invalidation),
        matching the per-operation methods.
        """
        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                yield _BatchPage(self, hass, printer)
                failed = False
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()

    async def print_text_with_image(
        self,
        hass: HomeAssistant,
        *,
        text_kwargs: dict[str, Any],
        image_kwargs: dict[str, Any],
        cut: str | None,
        feed: int | None,
        context: Context | None = None,
    ) -> None:
        """Print text and an image as a single atomic receipt.

        Pre-resolves the image bytes **outside** the lock so a slow
        camera doesn't monopolize the printer queue. Then takes the
        lock once and runs both halves under the same acquisition so
        no other caller can interleave between text and image.

        ``text_kwargs`` and ``image_kwargs`` are the per-half kwargs
        (without ``cut``/``feed`` — those are applied once at the end).
        """
        image_source = image_kwargs.pop("image")
        prepared = await prepare_image_for_print(
            self, hass, image_source, context=context, **image_kwargs
        )

        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                try:
                    await _print_text_under_lock(self, hass, printer, **text_kwargs)
                    await _print_prepared_under_lock(hass, printer, prepared)
                    await self._apply_cut_and_feed(hass, printer, cut, feed)
                    failed = False
                except asyncio.CancelledError, Exception:  # pragma: no cover (T-L4)
                    # S-M3: shield the cleanup so a second cancellation
                    # mid-flush doesn't leave paper half-printed. Only
                    # ``Exception`` is suppressed here — deliberately not
                    # ``CancelledError``: suppressing it would make this
                    # task swallow its own cancellation (``task.cancelled()``
                    # stays False), breaking ``asyncio.timeout()`` callers
                    # and HA's shutdown accounting. Known limitation: a
                    # *third* cancellation arriving while we wait on the
                    # shield raises CancelledError at this await point and
                    # runs the ``finally`` below, which releases/closes the
                    # transport while the shielded cut/feed task may still
                    # be writing to it. Fixing that requires re-awaiting the
                    # shielded future on the way out, not suppressing the
                    # cancellation.
                    #
                    # T-L4: not unit-tested. Triple-cancel races are
                    # notoriously hard to write deterministic tests for;
                    # the shield invariant is covered by manual
                    # cancellation testing during integration QA. If you
                    # remove or modify this shield, document why in the
                    # CHANGELOG so reviewers know the manual coverage
                    # bar moved.
                    with contextlib.suppress(Exception):
                        await asyncio.shield(
                            asyncio.ensure_future(
                                self._apply_cut_and_feed(hass, printer, cleanup_cut(cut), feed or 1)
                            )
                        )
                    raise
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        await self._mark_success()


class _BatchPage:
    """Print primitives bound to one held connection.

    Created only by :meth:`EscposPrinterAdapterBase.batch_connection`;
    valid only inside that ``with`` block. Never cuts — a batch page is
    a fragment stream, the caller feeds/cuts via :meth:`feed` or a
    follow-up operation.
    """

    def __init__(self, adapter: EscposPrinterAdapterBase, hass: HomeAssistant, printer: Any):
        self._adapter = adapter
        self._hass = hass
        self._printer = printer

    async def print_text(
        self,
        *,
        text: str,
        align: str | None = None,
        bold: bool | None = None,
        underline: str | None = None,
        width: str | int | None = None,
        height: str | int | None = None,
        encoding: str | None = None,
        wrap: bool = True,
        feed: int | None = 0,
    ) -> None:
        """Print text on the held connection (mirrors ``adapter.print_text``)."""
        await _print_text_under_lock(
            self._adapter,
            self._hass,
            self._printer,
            text=text,
            align=align,
            bold=bold,
            underline=underline,
            width=width,
            height=height,
            encoding=encoding,
            wrap=wrap,
        )
        await self._adapter._apply_cut_and_feed(self._hass, self._printer, "none", feed)

    async def print_qr(
        self,
        *,
        data: str,
        size: int | None = None,
        ec: str | None = None,
        align: str | None = "center",
    ) -> None:
        """Print a QR code on the held connection (mirrors ``adapter.print_qr``)."""
        await _qr_under_lock(self._hass, self._printer, data=data, size=size, ec=ec, align=align)

    async def print_image(
        self,
        *,
        image: str,
        impl: str | None = None,
        width: int | None = None,
        dither: str = "floyd-steinberg",
        auto_resize: bool = False,
        feed: int | None = 0,
        ignore_profile_width: bool = False,
    ) -> None:
        """Print an image on the held connection (mirrors ``adapter.print_image``).

        Image prep runs while the lock is held — callers pass small
        generated data URIs (calibration patterns), not slow camera or
        URL sources.

        ``ignore_profile_width`` swaps in a width-unlocked profile for
        the send so python-escpos doesn't refuse images wider than the
        profile's declared width — calibration's width bars are wider
        on purpose (hardware clipping is the measurement).
        """
        prepared = await prepare_image_for_print(
            self._adapter,
            self._hass,
            image,
            impl=impl,
            width=width,
            dither=dither,
            auto_resize=auto_resize,
        )
        if ignore_profile_width:
            with profile_width_bypass(self._printer):
                await _print_prepared_under_lock(self._hass, self._printer, prepared)
        else:
            await _print_prepared_under_lock(self._hass, self._printer, prepared)
        await self._adapter._apply_cut_and_feed(self._hass, self._printer, "none", feed)

    async def feed(self, lines: int) -> None:
        """Feed blank lines on the held connection."""
        await self._adapter._apply_cut_and_feed(self._hass, self._printer, "none", lines)
