"""Image preprocessing pipeline for thermal printing.

The pipeline applies EXIF orientation correction, alpha flattening,
grayscale conversion, optional rotation, width fitting against the
printer profile, optional autocontrast, and a choice of
dither/threshold conversion to 1-bit. The output is a PIL ``Image``
ready to hand to ``python-escpos``'s ``image()`` call.

Run synchronously on an executor thread; never call from the event loop.

The order of operations is deliberate: we convert to grayscale **before**
rotate/resize so the expensive LANCZOS pass runs in 1-channel mode rather
than 3-/4-channel RGB(A). For a typical 4096x3072 phone snapshot this is
a ~3-4x speedup and a ~3x cut in peak working memory.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import logging

from PIL import Image, ImageOps
import PIL.Image

from ..const import DEFAULT_DITHER, DEFAULT_THRESHOLD
from ..security import MAX_IMAGE_PIXELS, MAX_PROCESSED_HEIGHT

_LOGGER = logging.getLogger(__name__)

# Fallback when the printer profile reports no usable pixel width. 512 px
# is a worst-case-safe default for 58 mm thermals; 80 mm printers should
# override with their actual width (576) via the adapter base.
FALLBACK_PROFILE_WIDTH = 512

# Set Pillow's process-global pixel cap so DecompressionBombError fires
# deterministically on attacker-controlled images. This is a process-wide
# setting; the value here is the maximum across all PIL consumers in the
# Python process (Pillow checks ``> 2*MAX_IMAGE_PIXELS`` for the hard
# error and warns at ``> MAX_IMAGE_PIXELS``).
PIL.Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

# Pinned decoder allow-list for ``Image.open`` so we never invoke novelty
# or vulnerability-prone decoders on attacker-controlled bytes. HEIC /
# HEIF / AVIF are added at runtime when ``pillow-heif`` is importable
# — see ``_register_heif_opener`` below.
_DECODER_ALLOWLIST = ["PNG", "JPEG", "GIF", "BMP", "TIFF", "WEBP"]


def _register_heif_opener() -> tuple[str, ...]:
    """Register HEIC/AVIF support if ``pillow-heif`` is installed.

    HEIC is the default container for iPhone snapshots; without this hop
    a ``camera.<id>`` source from an iOS-fed camera proxy fails to
    decode. ``pillow-heif`` is a soft dependency — when it's missing we
    log a single debug message and proceed with the static allowlist so
    upgrades don't break existing setups.
    """
    try:
        from pillow_heif import register_heif_opener  # noqa: PLC0415
    except ImportError:
        _LOGGER.debug(
            "pillow-heif not installed; HEIC/AVIF source images will be rejected"
        )
        return ()
    register_heif_opener()
    return ("HEIF", "AVIF")


_DECODER_ALLOWLIST.extend(_register_heif_opener())

# Cache of precomputed 256-entry threshold LUTs keyed by threshold value
# so we avoid rebuilding the lambda LUT on every print.
_THRESHOLD_LUT_CACHE: dict[int, bytes] = {}


def _threshold_lut(threshold: int) -> bytes:
    """Return (and cache) the 256-byte LUT for a binarization threshold."""
    lut = _THRESHOLD_LUT_CACHE.get(threshold)
    if lut is None:
        lut = bytes(0 if p <= threshold else 255 for p in range(256))
        _THRESHOLD_LUT_CACHE[threshold] = lut
    return lut


@dataclass(slots=True, frozen=True, kw_only=True)
class ImageProcessOptions:
    """Options controlling the image processing pipeline."""

    width: int | None = None
    """Target width in pixels; if None, use ``profile_width`` (falls back to 512)."""

    profile_width: int | None = None
    """Printer profile's max pixel width, used when ``width`` is None."""

    rotation: int = 0
    """Rotation in degrees: 0, 90, 180, or 270 (clockwise)."""

    dither: str = DEFAULT_DITHER
    """One of ``floyd-steinberg``, ``none``, ``threshold``."""

    threshold: int = DEFAULT_THRESHOLD
    """1-254 threshold value when ``dither='threshold'``."""

    autocontrast: bool = False
    """Stretch contrast before B&W conversion."""

    invert: bool = False
    """Invert grayscale before B&W conversion (white ↔ black)."""

    mirror: bool = False
    """Horizontally mirror the image (useful for receipt windows)."""

    auto_resize: bool = False
    """If True, downscale the decoded image early before the size cap fires."""


def process_image(img: Image.Image, opts: ImageProcessOptions) -> Image.Image:
    """Apply the processing pipeline to ``img`` and return the result."""
    try:
        oriented = ImageOps.exif_transpose(img)
        if oriented is not None:
            img = oriented
    except (KeyError, AttributeError, TypeError, OSError):
        _LOGGER.debug("EXIF transpose failed; continuing with original")

    # auto_resize: knock huge phone snapshots down *before* the alpha
    # flatten + grayscale pass so we spend the LANCZOS budget on a small
    # image. Pick a conservative ceiling so we don't lose detail for
    # the eventual width-fit pass downstream.
    if opts.auto_resize:
        ceiling = max(
            opts.width or 0,
            opts.profile_width or 0,
            FALLBACK_PROFILE_WIDTH,
        )
        if img.width > ceiling * 4 or img.height > ceiling * 4:
            img.thumbnail(
                (ceiling * 4, ceiling * 4), Image.Resampling.LANCZOS
            )

    # Flatten alpha onto white — thermal prints black on white paper, so
    # transparent regions should read as white (not black).
    if img.mode in ("RGBA", "LA", "PA") or (
        img.mode == "P" and "transparency" in img.info
    ):
        rgba = img.convert("RGBA")
        background = Image.new("RGB", rgba.size, (255, 255, 255))
        background.paste(rgba, mask=rgba.split()[-1])
        img = background

    # Grayscale before rotate/resize so the expensive ops run on 1 byte
    # per pixel instead of 3-4.
    if img.mode != "L":
        img = img.convert("L")

    if opts.rotation:
        # PIL rotates counter-clockwise; user-facing degrees are clockwise.
        ccw_degrees = (360 - opts.rotation) % 360
        if ccw_degrees:
            img = img.rotate(ccw_degrees, expand=True)

    target_width = opts.width or opts.profile_width or FALLBACK_PROFILE_WIDTH
    if img.width > target_width:
        ratio = target_width / float(img.width)
        new_size = (target_width, max(1, int(img.height * ratio)))
        old_w, old_h = img.width, img.height
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        _LOGGER.debug(
            "Resized image from %dx%d to %dx%d", old_w, old_h, new_size[0], new_size[1]
        )

    if opts.autocontrast:
        img = ImageOps.autocontrast(img)

    if opts.invert:
        img = ImageOps.invert(img)

    if opts.mirror:
        img = ImageOps.mirror(img)

    # Bounds checked AFTER rotate/resize so expand=True can't sneak a
    # tall image past the schema-level cap. Error text suggests the two
    # concrete knobs the user can turn so they don't have to read source.
    if img.height > MAX_PROCESSED_HEIGHT:
        raise ValueError(
            f"Processed image height {img.height}px exceeds max "
            f"{MAX_PROCESSED_HEIGHT}px — reduce image_width or set "
            f"rotation=90/270 to print landscape"
        )

    if opts.dither == "floyd-steinberg":
        return img.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    if opts.dither == "none":
        return img.convert("1", dither=Image.Dither.NONE)
    if opts.dither == "threshold":
        return img.point(_threshold_lut(opts.threshold), mode="1")
    raise ValueError(f"Unknown dither mode: {opts.dither!r}")


def process_image_from_bytes(
    raw: bytes, opts: ImageProcessOptions
) -> Image.Image:
    """Decode ``raw`` and run :func:`process_image` on the result.

    Uses ``Image.open(..., formats=)`` to constrain the decoder allow-list.
    The returned image is always a freshly-constructed 1-bit image (step 8
    in :func:`process_image`), so it is safe to close ``src`` afterward.
    """
    with Image.open(io.BytesIO(raw), formats=_DECODER_ALLOWLIST) as src:
        src.load()
        return process_image(src, opts)
