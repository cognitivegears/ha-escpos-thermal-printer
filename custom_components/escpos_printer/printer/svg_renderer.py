"""Rasterise SVG bytes to PNG for the thermal print pipeline.

SVG documents are parsed via :func:`security.validate_svg_bytes` (which
uses :mod:`defusedxml` to reject XXE / billion-laughs / external-entity
expansion and to bound element count) before being handed to
``cairosvg``. The renderer runs with ``unsafe=False``, which makes
cairosvg auto-install its ``safe_fetch`` policy internally — every
external resource reference (``<image href="…">``, ``<use href="…">``,
CSS ``@import``) is replaced with an empty SVG, keeping the renderer
fully offline. ``output_width`` and ``output_height`` are both pinned
so that an SVG declaring a pathological aspect ratio (e.g.
``width="1" height="100000"``) cannot trick cairo into allocating a
multi-gigabyte surface.

The returned PNG is fed back into the existing ``image_processor``
pipeline (PIL decode → grayscale → resize → dither) so all of the
existing safety and width-fit logic still applies.
"""

from __future__ import annotations

import io
import logging
import os

from homeassistant.exceptions import HomeAssistantError

from ..security import MAX_PROCESSED_HEIGHT, sanitize_log_message, validate_svg_bytes

_LOGGER = logging.getLogger(__name__)

# Emergency kill-switch. Set this environment variable to anything
# truthy (``1``, ``true``, ``yes``) at HA startup to disable SVG
# rendering integration-wide without a code change — useful if a
# cairosvg / libcairo CVE drops between releases. Raster image
# printing is unaffected. Documented in
# ``docs/troubleshooting.md`` so admins can find it.
_KILL_SWITCH_ENV = "ESCPOS_DISABLE_SVG"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def _svg_disabled_by_env() -> bool:
    return os.environ.get(_KILL_SWITCH_ENV, "").strip().lower() in _TRUTHY


def rasterise_svg_to_png(raw: bytes, *, output_width: int) -> bytes:
    """Validate ``raw`` SVG bytes and render them to a PNG byte string.

    Both ``output_width`` and ``MAX_PROCESSED_HEIGHT`` are passed to
    cairosvg, so the rasterised surface is bounded in both dimensions
    regardless of the SVG's declared width/height. Blocking — call
    from an executor thread.

    Honors the ``ESCPOS_DISABLE_SVG`` environment variable as an
    emergency kill-switch: if set, raises immediately so SVG never
    reaches defusedxml or cairosvg. Raster prints are unaffected.
    """
    if _svg_disabled_by_env():
        raise HomeAssistantError(
            "SVG rendering is disabled (ESCPOS_DISABLE_SVG is set); "
            "use a raster source (PNG / JPEG) instead"
        )
    validated = validate_svg_bytes(raw)

    # Lazy import so the cairosvg dependency (and its libcairo binding)
    # is only touched when SVG actually arrives. Keeps unit tests for
    # raster-image paths runnable on systems without libcairo.
    try:
        import cairosvg  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - cairosvg is a pinned runtime dep
        raise HomeAssistantError("SVG support requires cairosvg") from exc

    bio = io.BytesIO()
    try:
        cairosvg.svg2png(
            bytestring=validated,
            write_to=bio,
            output_width=output_width,
            output_height=MAX_PROCESSED_HEIGHT,
            unsafe=False,
        )
    except (MemoryError, SystemError):
        # Allocation failures from cairo's surface backend deserve to
        # propagate so the HA supervisor / process monitor can react;
        # do not swallow into a generic "Failed to rasterise SVG" string.
        raise
    except Exception as exc:
        # Surface the underlying exception class in the message so
        # support logs distinguish "TypeError" (wrong cairosvg API),
        # "CairoError" (libcairo resource limit), "ValueError" (CVE-
        # 2026-31899 ``<use>`` cap), and so on. The message body still
        # goes through ``sanitize_log_message`` for the usual scrubbing.
        kind = type(exc).__name__
        raise HomeAssistantError(
            f"Failed to rasterise SVG ({kind}): {sanitize_log_message(str(exc))}"
        ) from exc

    return bio.getvalue()


__all__ = ["rasterise_svg_to_png"]
