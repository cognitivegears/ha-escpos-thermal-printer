"""Image-print operation mixin for ESC/POS printer adapters.

Split from ``print_operations`` so the text/QR fast path stays small
and the image pipeline can grow features (cancellation cleanup, lazy
slicing, ``MAX_SLICES`` guardrails) without bloating the text mixin.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
import inspect
import logging
from typing import TYPE_CHECKING, Any, NamedTuple

from homeassistant.exceptions import HomeAssistantError
from PIL import UnidentifiedImageError

from ..const import (
    DEFAULT_CUT,
    DEFAULT_FRAGMENT_HEIGHT,
    DEFAULT_IMPL,
)
from ..image_sources import classify_source, resolve_image_bytes
from ..security import (
    MAX_SLICES,
    sanitize_log_message,
    validate_dither_mode,
    validate_impl_mode,
    validate_numeric_input,
    validate_rotation,
)
from ._host import _PrinterHost
from .image_processor import (
    _DECODER_ALLOWLIST,
    FALLBACK_PROFILE_WIDTH,
    ImageProcessOptions,
    process_image_from_bytes,
)
from .mapping_utils import cleanup_cut, map_align

if TYPE_CHECKING:
    from collections.abc import Iterator

    from homeassistant.core import Context, HomeAssistant
    from PIL import Image

_LOGGER = logging.getLogger(__name__)


class PreparedImage(NamedTuple):
    """Image-pipeline result + per-slice send params, ready for the printer."""

    img_obj: Image.Image
    slice_count: int
    align_m: str
    high_density: bool
    impl: str
    center: bool
    fragment_height: int
    chunk_delay_ms: int


async def prepare_image_for_print(
    host: _PrinterHost,
    hass: HomeAssistant,
    image: str,
    *,
    high_density: bool = True,
    align: str | None = None,
    width: int | None = None,
    rotation: int = 0,
    dither: str = "floyd-steinberg",
    threshold: int = 128,
    impl: str | None = None,
    center: bool = False,
    autocontrast: bool = False,
    invert: bool = False,
    mirror: bool = False,
    auto_resize: bool = False,
    fallback_image: str | None = None,
    fragment_height: int | None = None,
    chunk_delay_ms: int | None = None,
    context: Context | None = None,
) -> PreparedImage:
    """Resolve, validate, and decode an image for printing.

    Done outside the printer lock so a slow camera/HTTP fetch doesn't
    monopolize the printer queue.

    Per-printer reliability profile defaults are consulted when the
    caller leaves ``impl`` / ``fragment_height`` / ``chunk_delay_ms``
    unset. The transport's ``default_chunk_delay_ms`` is the final
    fallback so Bluetooth printers get 50 ms even with no profile.

    If ``fallback_image`` is set, a failure to resolve ``image`` (camera
    unavailable, network error, file missing) re-runs the resolve step
    against the fallback exactly once. The fallback uses the same
    processing options so dither/threshold/etc. stay consistent.
    """
    dither = validate_dither_mode(dither)
    rotation = validate_rotation(rotation)
    if width is not None:
        width = validate_numeric_input(width, 16, 2048, "width")
    threshold = validate_numeric_input(threshold, 1, 254, "threshold")

    profile_defaults = getattr(host, "reliability_profile_defaults", {}) or {}
    if impl is None:
        # Resolution chain: legacy per-profile-preset impl (presets no
        # longer carry one, but honor it if present) -> adapter's
        # per-entry default (CONF_IMPL / pick_impl) -> hard-coded default.
        impl = profile_defaults.get("impl") or getattr(host, "default_impl", None) or DEFAULT_IMPL
    if getattr(host, "profile_no_image_support", False) and not getattr(
        host, "_no_image_warned", True
    ):
        _LOGGER.warning(
            "Printer profile reports no image support; attempting impl=%s anyway",
            impl,
        )
        host._no_image_warned = True
    if fragment_height is None:
        fragment_height = profile_defaults.get("fragment_height", DEFAULT_FRAGMENT_HEIGHT)
    if chunk_delay_ms is None:
        if "chunk_delay_ms" in profile_defaults:
            chunk_delay_ms = profile_defaults["chunk_delay_ms"]
        else:
            chunk_delay_ms = getattr(host, "default_chunk_delay_ms", 0)

    impl = validate_impl_mode(impl)
    fragment_height = validate_numeric_input(fragment_height, 16, 1024, "fragment_height")
    chunk_delay_ms = validate_numeric_input(chunk_delay_ms, 0, 5000, "chunk_delay_ms")

    stats = getattr(host, "_image_stats", None)

    process_opts = ImageProcessOptions(
        width=width,
        profile_width=host.get_profile_pixel_width(hass),
        rotation=rotation,
        dither=dither,
        threshold=threshold,
        autocontrast=autocontrast,
        invert=invert,
        mirror=mirror,
        auto_resize=auto_resize,
    )
    allow_local = bool(getattr(host, "allow_local_image_urls", False))
    try:
        if stats is not None:
            kind, _ = classify_source(image)
            stats.last_source_kind = kind
        raw, content_type = await _resolve_with_retry(
            hass,
            image,
            context=context,
            auto_resize=auto_resize,
            fallback=fallback_image,
            allow_local=allow_local,
        )
        img_obj = await _process_bytes(hass, raw, process_opts, content_type=content_type)
        raw_len = len(raw)
        del raw

        slice_count = (img_obj.height + fragment_height - 1) // fragment_height
        if slice_count > MAX_SLICES:
            raise HomeAssistantError(
                f"Refusing to print: image would require {slice_count} chunks "
                f"(max {MAX_SLICES}); reduce image_width, lower the source "
                f"resolution, or raise fragment_height"
            )
        if stats is not None:
            stats.last_decoded_dims = (img_obj.width, img_obj.height)
            stats.last_decoded_bytes = raw_len
            stats.last_slice_count = slice_count
    except Exception as err:
        if stats is not None:
            stats.total_failures += 1
            stats.last_error_class = type(err).__name__
        raise

    return PreparedImage(
        img_obj=img_obj,
        slice_count=slice_count,
        align_m=map_align(align),
        high_density=high_density,
        impl=impl,
        center=center,
        fragment_height=fragment_height,
        chunk_delay_ms=chunk_delay_ms,
    )


async def _try_fallback(
    hass: HomeAssistant,
    fallback: str | None,
    primary: HomeAssistantError,
    *,
    context: Context | None,
    auto_resize: bool,
    allow_local: bool = False,
) -> tuple[bytes, str | None]:
    """Run ``fallback`` if set; raise the primary error on any failure.

    Returning the primary preserves the diagnostic the user is most
    likely to want — the fallback existed precisely because the
    primary might fail.
    """
    if fallback:
        _LOGGER.debug("Primary image resolve failed (%s); trying fallback", type(primary).__name__)
        try:
            return await resolve_image_bytes(
                hass, fallback, context=context, auto_resize=auto_resize, allow_local=allow_local
            )
        except HomeAssistantError:
            raise primary from None
    raise primary


async def _resolve_with_retry(
    hass: HomeAssistant,
    image: str,
    *,
    context: Context | None,
    auto_resize: bool,
    fallback: str | None,
    allow_local: bool = False,
) -> tuple[bytes, str | None]:
    """Resolve ``image``; retry once on transient camera/http failure.

    For camera/http sources (where the upstream may need a beat to
    warm up), retry once with a 0.5s back-off — unless the failure
    was already a TimeoutError, in which case the upstream demonstrably
    needs more than 10s and another half-second will not help
    (P-M4). Otherwise the original error is returned along with any
    fallback diagnostic.

    For local/file/data sources retry is meaningless; fall through to
    the fallback (if any).
    """
    try:
        return await resolve_image_bytes(
            hass, image, context=context, auto_resize=auto_resize, allow_local=allow_local
        )
    except HomeAssistantError as primary:
        kind, _ = classify_source(image)
        retryable = kind in ("camera", "http") and not _is_timeout_cause(primary)
        if retryable:
            _LOGGER.debug(
                "Transient image resolve failure (%s); retrying once",
                type(primary).__name__,
            )
            await asyncio.sleep(0.5)
            with contextlib.suppress(HomeAssistantError):
                return await resolve_image_bytes(
                    hass, image, context=context, auto_resize=auto_resize, allow_local=allow_local
                )
        return await _try_fallback(
            hass,
            fallback,
            primary,
            context=context,
            auto_resize=auto_resize,
            allow_local=allow_local,
        )


def _is_timeout_cause(err: BaseException) -> bool:
    """Return True if ``err`` (or its cause chain) wraps a timeout.

    P-M4: a 10 s HTTP/camera timeout is strong evidence the upstream
    is not "transient slow" — it's "not ready" — so retrying in 0.5 s
    just burns another 10 s before the fallback fires. Detecting a
    timeout in the cause chain lets us skip straight to the fallback.
    """
    seen: set[int] = set()
    current: BaseException | None = err
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, (TimeoutError, asyncio.TimeoutError)):
            return True
        # aiohttp wraps the underlying timeout; check the message as a
        # belt-and-braces signal since the cause may be lost when the
        # outer HomeAssistantError is constructed from a string.
        if "timeout" in str(current).lower():
            return True
        current = current.__cause__ or current.__context__
    return False


class ImageOperationsMixin:
    """Mixin providing :meth:`print_image`."""

    async def print_image(
        self: _PrinterHost,
        hass: HomeAssistant,
        *,
        image: str,
        high_density: bool = True,
        align: str | None = None,
        cut: str | None = DEFAULT_CUT,
        feed: int | None = 0,
        width: int | None = None,
        rotation: int = 0,
        dither: str = "floyd-steinberg",
        threshold: int = 128,
        impl: str | None = None,
        center: bool = False,
        autocontrast: bool = False,
        invert: bool = False,
        mirror: bool = False,
        auto_resize: bool = False,
        fallback_image: str | None = None,
        fragment_height: int | None = None,
        chunk_delay_ms: int | None = None,
        context: Context | None = None,
    ) -> None:
        """Print an image to the printer.

        Resolves the source (URL, local path, camera/image entity,
        base64 data URI), preprocesses it (EXIF orientation, alpha
        flatten, rotate, resize, dither/threshold), then streams it to
        the printer in fixed-height chunks separated by
        ``chunk_delay_ms`` to avoid buffer overruns on long images
        (issues #45 / #43).

        ``context`` (the HA ``ServiceCall.context``) is forwarded to
        ``resolve_image_bytes`` so camera/image entity reads respect the
        calling user's per-entity permissions.
        """
        prepared = await prepare_image_for_print(
            self,
            hass,
            image,
            high_density=high_density,
            align=align,
            width=width,
            rotation=rotation,
            dither=dither,
            threshold=threshold,
            impl=impl,
            center=center,
            autocontrast=autocontrast,
            invert=invert,
            mirror=mirror,
            auto_resize=auto_resize,
            fallback_image=fallback_image,
            fragment_height=fragment_height,
            chunk_delay_ms=chunk_delay_ms,
            context=context,
        )
        _LOGGER.debug(
            "print_image processed: size=%dx%d impl=%s dither=%s chunks=%d delay=%dms",
            prepared.img_obj.width,
            prepared.img_obj.height,
            prepared.impl,
            dither,
            prepared.slice_count,
            prepared.chunk_delay_ms,
        )

        stats = getattr(self, "_image_stats", None)
        async with self._lock:
            printer, owned = await self._acquire_printer_or_offline(hass)
            failed = True
            try:
                try:
                    await _print_prepared_under_lock(hass, printer, prepared)
                    await self._apply_cut_and_feed(hass, printer, cut, feed)
                    failed = False
                except (asyncio.CancelledError, Exception) as err:
                    # Best-effort cleanup so a cancelled mid-print doesn't
                    # leave paper hanging mid-image.
                    if stats is not None:
                        stats.total_failures += 1
                        stats.last_error_class = type(err).__name__
                    with contextlib.suppress(Exception):
                        await self._apply_cut_and_feed(hass, printer, cleanup_cut(cut), feed or 1)
                    raise
            finally:
                await self._release_printer(hass, printer, owned=owned, failed=failed)
        if stats is not None:
            stats.total_prints += 1
            stats.last_error_class = None
        await self._mark_success()


# ---------------------------------------------------------------------------
# Internal helpers (module-level so they're testable without an adapter).
# ---------------------------------------------------------------------------


def _describe_undecodable(raw: bytes, content_type: str | None) -> str:
    """Build an actionable error for bytes PIL could not identify.

    Pillow's own ``UnidentifiedImageError`` text ("cannot identify image
    file <_io.BytesIO …>") tells the user nothing about *what* came back.
    The usual culprit for a URL source is a CDN/WAF answering with an
    HTML error or block page served as 200, so surface the declared
    content type and byte count. The leading-byte sniff itself only goes
    to the debug log -- echoing fetched response bytes back to the
    service caller would turn this error into a content oracle for
    SSRF-adjacent probing.
    """
    sniff = bytes(raw[:16])
    looks_html = sniff.lstrip()[:1] == b"<"
    _LOGGER.debug("Undecodable image bytes starts with: %r", sniff)
    detail = f"content-type {content_type!r}, {len(raw)} bytes"
    hint = (
        " — the server appears to have returned an HTML page (error/bot-block) instead of the image"
        if looks_html or (content_type or "").lower().startswith("text/")
        else ""
    )
    return (
        f"Source did not return a decodable image ({detail}){hint}. "
        f"Supported formats: {', '.join(_DECODER_ALLOWLIST)}."
    )


async def _process_bytes(
    hass: HomeAssistant,
    raw: bytes,
    opts: ImageProcessOptions,
    *,
    content_type: str | None = None,
) -> Image.Image:
    """Run ``process_image_from_bytes`` on an executor thread."""

    def _go() -> Image.Image:
        try:
            return process_image_from_bytes(raw, opts)
        except UnidentifiedImageError as exc:
            raise HomeAssistantError(_describe_undecodable(raw, content_type)) from exc

    return await hass.async_add_executor_job(_go)


class _WidthUnlockedProfile:
    """Proxy of a python-escpos profile with ``media.width`` removed.

    ``Escpos.image()`` raises ``ImageWidthError`` for images wider than
    ``profile_data["media"]["width"]["pixels"]`` — and deliberately
    prints anyway on ``KeyError`` (the "unknown width" path generic
    profiles take). Dropping just that key opts out of the refusal while
    delegating every other attribute (``get_font``, ``supports``, …) to
    the real profile, so ``set()`` and text encoding keep working.
    """

    def __init__(self, profile: Any) -> None:
        self._profile = profile
        data = dict(getattr(profile, "profile_data", {}) or {})
        media = dict(data.get("media", {}))
        media.pop("width", None)
        data["media"] = media
        self.profile_data = data

    def __getattr__(self, name: str) -> Any:
        return getattr(self._profile, name)


@contextlib.contextmanager
def profile_width_bypass(printer: Any) -> Iterator[None]:
    """Temporarily hide the profile's pixel width from ``printer``.

    Calibration sends bars *deliberately* wider than the profile width
    so the hardware's own clipping can be measured — including when the
    configured profile under-declares the true width, which is exactly
    the misconfiguration the width step exists to catch. Callers hold
    the adapter lock, so no other operation can observe the swapped
    profile.
    """
    original = printer.profile
    printer.profile = _WidthUnlockedProfile(original)
    try:
        yield
    finally:
        printer.profile = original


# Cache of ``printer.image`` supported kwarg names, keyed by printer class.
# ``None`` means "accepts arbitrary kwargs" (a ``**kwargs`` parameter, or a
# signature we couldn't introspect — e.g. a test double), so the full kwarg
# set is passed through unfiltered.
_IMAGE_KWARGS_CACHE: dict[type, frozenset[str] | None] = {}


def _supported_image_kwargs(printer: Any) -> frozenset[str] | None:
    """Return the keyword-argument names ``printer.image`` accepts (cached).

    Older python-escpos releases lack ``impl``/``fragment_height``/``center``
    on ``Escpos.image``. Probing the signature up front — instead of calling
    with the full kwarg set and retrying on ``TypeError`` — means a
    signature mismatch can never risk sending the image bytes twice (the
    ``TypeError`` could originate deeper in python-escpos *after* some bytes
    were already written to the transport).
    """
    cls = type(printer)
    if cls in _IMAGE_KWARGS_CACHE:
        return _IMAGE_KWARGS_CACHE[cls]
    try:
        params = inspect.signature(printer.image).parameters.values()
    except TypeError, ValueError:
        supported: frozenset[str] | None = None
    else:
        if any(p.kind is p.VAR_KEYWORD for p in params):
            supported = None
        else:
            supported = frozenset(
                p.name for p in params if p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
            )
    _IMAGE_KWARGS_CACHE[cls] = supported
    return supported


async def _send_image_slice(
    hass: HomeAssistant,
    printer: Any,
    fragment: Image.Image,
    *,
    is_first: bool,
    align_m: str,
    high_density: bool,
    impl: str,
    center: bool,
) -> None:
    """Send one image slice to the printer."""

    def _do(p: Any) -> None:
        if is_first and hasattr(p, "set"):
            p.set(align=align_m, normal_textsize=True)
        if not hasattr(p, "image"):
            p.text("[image printing not supported by this printer]\n")
            return
        # ``fragment_height = height + 1`` tells python-escpos "don't
        # re-split this chunk" — we've already sliced at the desired
        # boundary (issues #45 / #43).
        kwargs = {
            "high_density_vertical": high_density,
            "high_density_horizontal": high_density,
            "impl": impl,
            "fragment_height": fragment.height + 1,
            "center": center,
        }
        supported = _supported_image_kwargs(p)
        if supported is not None:
            kwargs = {k: v for k, v in kwargs.items() if k in supported}
        p.image(fragment, **kwargs)

    await hass.async_add_executor_job(_do, printer)


async def _print_image_under_lock(
    hass: HomeAssistant,
    printer: Any,
    *,
    img_obj: Image.Image,
    align_m: str,
    high_density: bool,
    impl: str,
    center: bool,
    fragment_height: int,
    chunk_delay_ms: int,
) -> None:
    """Slice and stream ``img_obj`` to the printer. Caller holds the lock."""
    if img_obj.height <= fragment_height:
        await _send_image_slice(
            hass,
            printer,
            img_obj,
            is_first=True,
            align_m=align_m,
            high_density=high_density,
            impl=impl,
            center=center,
        )
        return

    total = (img_obj.height + fragment_height - 1) // fragment_height
    for index in range(total):
        top = index * fragment_height
        bottom = min(top + fragment_height, img_obj.height)
        fragment = img_obj.crop((0, top, img_obj.width, bottom))
        try:
            if index > 0 and chunk_delay_ms > 0:
                await asyncio.sleep(chunk_delay_ms / 1000.0)
            await _send_image_slice(
                hass,
                printer,
                fragment,
                is_first=(index == 0),
                align_m=align_m,
                high_density=high_density,
                impl=impl,
                center=center,
            )
        except Exception as err:
            _LOGGER.debug(
                "Image slice %d/%d failed: %s",
                index + 1,
                total,
                sanitize_log_message(str(err)),
            )
            raise
        finally:
            fragment.close()


async def _print_prepared_under_lock(
    hass: HomeAssistant, printer: Any, prepared: PreparedImage
) -> None:
    """Send a :class:`PreparedImage` to the printer. Caller holds the lock."""
    await _print_image_under_lock(
        hass,
        printer,
        img_obj=prepared.img_obj,
        align_m=prepared.align_m,
        high_density=prepared.high_density,
        impl=prepared.impl,
        center=prepared.center,
        fragment_height=prepared.fragment_height,
        chunk_delay_ms=prepared.chunk_delay_ms,
    )


@dataclass(slots=True)
class ImageStats:
    """Counters and snapshot fields for image-pipeline diagnostics.

    Captures only enums and shapes — never URLs, paths, or content —
    so this dict can land in diagnostics without leaking sensitive data
    (paths/URLs are redacted by ``security.sanitize_log_message`` if
    they ever surface in ``last_error_class``).
    """

    last_source_kind: str | None = None
    last_decoded_dims: tuple[int, int] | None = None
    last_decoded_bytes: int | None = None
    last_slice_count: int | None = None
    last_transport: str | None = None
    last_error_class: str | None = None
    total_prints: int = 0
    total_failures: int = 0

    def as_dict(self) -> dict[str, Any]:
        """Render to a JSON-safe dict for diagnostics."""
        return {
            "last_source_kind": self.last_source_kind,
            "last_decoded_dims": list(self.last_decoded_dims) if self.last_decoded_dims else None,
            "last_decoded_bytes": self.last_decoded_bytes,
            "last_slice_count": self.last_slice_count,
            "last_transport": self.last_transport,
            "last_error_class": self.last_error_class,
            "total_prints": self.total_prints,
            "total_failures": self.total_failures,
        }


# Re-export ``FALLBACK_PROFILE_WIDTH`` so callers don't need to import
# from ``image_processor`` separately.
__all__ = ["FALLBACK_PROFILE_WIDTH", "ImageOperationsMixin", "ImageStats"]
