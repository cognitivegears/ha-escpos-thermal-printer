"""Render Unicode text to a 1-bit-friendly PIL image with custom fonts.

The output image is sized to fit the wrapped text exactly and is in mode
``"L"`` (grayscale) so the downstream image pipeline's threshold/dither
step decides binarization. Optional rotation (0/90/180/270 degrees,
clockwise from the user's perspective) is applied with ``expand=True``
so the bounding box grows to fit the rotated content.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
import math
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from ..security import MAX_RENDER_HEIGHT_PX, MAX_RENDER_PIXELS, open_local_font_no_follow

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

BuiltinFont = Literal["dejavu_mono", "dejavu_sans", "dejavu_serif"]
BUILTIN_FONTS: tuple[BuiltinFont, ...] = ("dejavu_mono", "dejavu_sans", "dejavu_serif")

# Resolved at import time so callers cannot bypass the bundled-font set by
# passing arbitrary names. The actual ``.ttf`` files live in ``../fonts/``
# relative to this module.
_FONTS_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "fonts"

_BUILTIN_FONT_FILES: Final[dict[str, str]] = {
    "dejavu_mono": "DejaVuSansMono.ttf",
    "dejavu_sans": "DejaVuSans.ttf",
    "dejavu_serif": "DejaVuSerif.ttf",
}


@dataclass(frozen=True, slots=True)
class _Resolved:
    path: str
    name: str


def _resolve_font(*, font_name: str | None, font_path: str | None) -> _Resolved:
    """Pick which TTF/OTF file to load.

    ``font_path`` takes precedence (it has already been validated by the
    handler). Otherwise ``font_name`` must be one of ``BUILTIN_FONTS`` —
    the schema layer (``vol.In(sorted(BUILTIN_FONT_CHOICES))``) enforces
    this for service callers, so reaching here with an unknown name is a
    bug (drift between this module and ``const.BUILTIN_FONT_CHOICES``).
    A-M3: raise loudly rather than silently falling back to mono so the
    drift is caught instead of masked.
    """
    if font_path:
        return _Resolved(path=str(font_path), name="custom")
    chosen = font_name or "dejavu_mono"
    if chosen not in _BUILTIN_FONT_FILES:
        raise ValueError(
            f"unknown bundled font {chosen!r}; expected one of {sorted(_BUILTIN_FONT_FILES)}"
        )
    file_name = _BUILTIN_FONT_FILES[chosen]
    return _Resolved(path=str(_FONTS_DIR / file_name), name=chosen)


# P-M3: user-supplied fonts go through ``open_local_font_no_follow`` and
# get wrapped in ``BytesIO`` so Pillow's implicit ``(path, idx)`` cache
# never sees them — meaning every call re-parses up to MAX_FONT_SIZE_BYTES
# of TTF/OTF data. Cache the parsed ``ImageFont`` per
# ``(resolved_path, mtime_ns, font_size)`` to amortise that cost. Bound at
# 8 entries (~8x5 MB worst-case FreeType state).
@lru_cache(maxsize=8)
def _cached_custom_font(path: str, mtime_ns: int, font_size: int) -> Any:
    """Parse and cache a user-supplied font via O_NOFOLLOW read.

    The ``mtime_ns`` key invalidates the cache when the file changes,
    so editing the TTF in place doesn't get a stale cached parse. The
    bytes are kept inside the ``ImageFont`` object — re-reading the
    path is not needed.
    """
    from PIL import ImageFont  # noqa: PLC0415

    font_data = open_local_font_no_follow(Path(path))
    return ImageFont.truetype(BytesIO(font_data), font_size)


def _measure(font: Any, text: str) -> tuple[int, int]:
    """Return ``(width, height)`` of ``text`` rendered with ``font``.

    Uses ``getbbox`` which Pillow 10+ exposes on both FreeType and the
    default bitmap font. Falls back to ``getlength`` if ``getbbox`` is
    unavailable for some reason (e.g. PIL stub).
    """
    if not text:
        return 0, 0
    if hasattr(font, "getbbox"):
        left, top, right, bottom = font.getbbox(text)
        return max(0, right - left), max(0, bottom - top)
    if hasattr(font, "getsize"):
        size = font.getsize(text)
        return int(size[0]), int(size[1])
    return len(text) * 8, 16


def _char_split(word: str, font: Any, max_width_px: int) -> list[str]:
    """Break ``word`` into chunks each fitting ``max_width_px`` wide.

    Returns one or more strings; the last is the trailing fragment that
    the caller continues building its current line with. Uses
    ``font.getlength`` when available so each character is measured
    once (O(N) total) instead of re-measuring ``buf + ch`` (O(N²)).
    For monospaced fonts the result is exact; for proportional fonts
    the wrap is conservative because per-char advances ignore kerning
    — acceptable given the alternative is multi-second wrap times on
    long tokens.
    """
    if not word:
        return [""]
    getlength = getattr(font, "getlength", None)
    chunks: list[str] = []
    buf_chars: list[str] = []
    buf_w = 0
    for ch in word:
        if getlength is not None:
            try:
                # Round up — per-char ``getlength`` returns advance
                # widths; cumulative bbox of the joined string can be a
                # hair wider than the sum of truncated per-char widths.
                ch_w = max(1, math.ceil(getlength(ch)))
            except (TypeError, ValueError):
                ch_w, _ = _measure(font, ch)
        else:
            ch_w, _ = _measure(font, ch)
        if buf_chars and buf_w + ch_w > max_width_px:
            chunks.append("".join(buf_chars))
            buf_chars = [ch]
            buf_w = ch_w
        else:
            buf_chars.append(ch)
            buf_w += ch_w
    chunks.append("".join(buf_chars))
    return chunks


def _word_width(word: str, font: Any) -> int:
    """Return the pixel advance of ``word`` using ``getlength`` when available."""
    if not word:
        return 0
    getlength = getattr(font, "getlength", None)
    if getlength is not None:
        try:
            measured: int = max(0, math.ceil(getlength(word)))
        except (TypeError, ValueError):
            measured = -1
        if measured >= 0:
            return measured
    width, _ = _measure(font, word)
    return width


def _wrap_to_pixels(text: str, font: Any, max_width_px: int) -> list[str]:
    """Word-wrap ``text`` so every output line fits ``max_width_px`` wide.

    Falls back to character-level chunking for tokens that are wider on
    their own than ``max_width_px`` (e.g. a very long URL). This mirrors
    ``textwrap``'s ``break_long_words=True`` default but in pixel space.

    Measures each word once and accumulates the running line width
    (``+ space + word``) per iteration — O(N) per paragraph rather than
    re-measuring the joined ``line + " " + word`` candidate each step,
    which was O(N²) and pinned the executor on long paragraphs.
    Kerning between the last char of ``line`` and the first of ``word``
    is ignored in the accumulated width; the few-pixel error is the
    same trade-off ``_char_split`` already accepts, and the conservative
    direction means lines wrap slightly early rather than over-flowing.
    """
    if max_width_px <= 0:
        return [text]
    space_w = _word_width(" ", font)
    out: list[str] = []
    for paragraph in text.splitlines() or [""]:
        if not paragraph:
            out.append("")
            continue
        line_parts: list[str] = []
        line_w = 0
        for word in paragraph.split(" "):
            word_w = _word_width(word, font)
            extra = word_w if not line_parts else space_w + word_w
            if line_w + extra <= max_width_px:
                line_parts.append(word)
                line_w += extra
                continue
            # The candidate is too wide. Flush the current line first
            # (if any), then decide whether ``word`` fits on a fresh
            # line or needs to be char-split.
            if line_parts:
                out.append(" ".join(line_parts))
                line_parts = []
                line_w = 0
            if word_w <= max_width_px:
                line_parts = [word]
                line_w = word_w
            else:
                chunks = _char_split(word, font, max_width_px)
                # Emit all but the last chunk; carry the trailing
                # fragment so subsequent words may still join it.
                out.extend(chunks[:-1])
                line_parts = [chunks[-1]]
                line_w = _word_width(chunks[-1], font)
        out.append(" ".join(line_parts))
    return out


def render_text_image(
    text: str,
    *,
    font_name: str | None = None,
    font_path: str | None = None,
    font_size: int = 16,
    max_width_px: int = 384,
    line_spacing: float = 1.1,
    rotation: int = 0,
    align: str = "left",
) -> PILImage:
    """Render ``text`` to a grayscale PIL image with the requested font.

    ``max_width_px`` is interpreted as the printed-output width (i.e. the
    paper width). For ``rotation`` 0/180 that equals the canvas width and
    text wraps to fit. For 90/270 the canvas is rotated before printing,
    so the canvas's *height* becomes the printed width (capped at
    ``max_width_px``) and its width runs along the paper feed — wrapping
    uses ``MAX_RENDER_HEIGHT_PX`` so a long line flows down the receipt
    instead of breaking at the paper width.

    Rotation is applied last with ``expand=True`` so the rotated canvas
    resizes to its new bounding box. The returned image is mode ``"L"``
    (8-bit grayscale, 255 = paper, 0 = ink) — the downstream image
    pipeline binarizes it.
    """
    # Imported lazily so unit tests that mock the renderer don't pay the
    # PIL import cost, and so the module imports cleanly even if Pillow
    # is missing (the handler short-circuits before this is called).
    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    if font_size < 1:
        raise ValueError(f"font_size must be >= 1, got {font_size}")
    if max_width_px < 1:
        raise ValueError(f"max_width_px must be >= 1, got {max_width_px}")
    if rotation not in (0, 90, 180, 270):
        raise ValueError(f"rotation must be one of 0/90/180/270, got {rotation}")
    if align not in ("left", "center", "right"):
        raise ValueError(f"align must be left/center/right, got {align!r}")
    if line_spacing < 0.5:
        raise ValueError(f"line_spacing must be >= 0.5, got {line_spacing}")

    resolved = _resolve_font(font_name=font_name, font_path=font_path)
    try:
        if font_path:
            # P-M3: cache the parsed ImageFont per (path, mtime_ns, size)
            # since BytesIO defeats Pillow's implicit FreeType face cache.
            # mtime_ns picks up edits in place; lru_cache(maxsize=8)
            # bounds the FreeType state held in memory.
            try:
                mtime_ns = os.stat(resolved.path).st_mtime_ns
            except OSError as exc:
                raise ValueError(
                    f"Could not load font {resolved.name!r}: {exc}"
                ) from exc
            font = _cached_custom_font(resolved.path, mtime_ns, font_size)
        else:
            font = ImageFont.truetype(resolved.path, font_size)
    except OSError as exc:
        raise ValueError(f"Could not load font {resolved.name!r}: {exc}") from exc

    rotated = rotation in (90, 270)
    # For 90/270 the canvas's width axis runs along the paper feed (long
    # axis), so wrap to MAX_RENDER_HEIGHT_PX rather than paper width.
    wrap_width_px = MAX_RENDER_HEIGHT_PX if rotated else max_width_px
    lines = _wrap_to_pixels(text, font, wrap_width_px)
    # Use the font ascent/descent so empty paragraphs still occupy a line.
    if hasattr(font, "getmetrics"):
        ascent, descent = font.getmetrics()
        single_line_h = ascent + descent
    else:
        _, single_line_h = _measure(font, "Mg")
        single_line_h = max(single_line_h, font_size)
    line_h = max(1, round(single_line_h * line_spacing))
    total_h = max(line_h, line_h * len(lines))

    if rotated:
        # Canvas tightly wraps the longest line; after 90/270° rotation
        # the canvas height (= total_h) becomes the printed width and must
        # fit the paper. The canvas width (= longest line) becomes the
        # length along the feed and is bounded by MAX_RENDER_HEIGHT_PX.
        canvas_w = max(
            (_measure(font, line)[0] for line in lines),
            default=0,
        )
        canvas_w = max(canvas_w, 1)
    else:
        canvas_w = max_width_px

    feed_axis_extent = canvas_w if rotated else total_h
    if feed_axis_extent > MAX_RENDER_HEIGHT_PX:
        raise ValueError(
            f"rendered text extent {feed_axis_extent}px along paper feed "
            f"exceeds maximum {MAX_RENDER_HEIGHT_PX}px (reduce text length "
            f"or font_size)"
        )
    if rotated and total_h > max_width_px:
        raise ValueError(
            f"rotated text stack height {total_h}px exceeds paper width "
            f"{max_width_px}px (reduce font_size, line_spacing, or line count)"
        )
    if canvas_w * total_h > MAX_RENDER_PIXELS:
        raise ValueError(
            f"rendered text canvas {canvas_w}x{total_h} "
            f"exceeds maximum {MAX_RENDER_PIXELS} pixels"
        )

    img = Image.new("L", (canvas_w, total_h), color=255)
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        w, _ = _measure(font, line)
        if align == "right":
            x = max(0, canvas_w - w)
        elif align == "center":
            x = max(0, (canvas_w - w) // 2)
        else:
            x = 0
        draw.text((x, i * line_h), line, fill=0, font=font)

    if rotation:
        # PIL rotates counter-clockwise; convert user-facing clockwise.
        ccw = (360 - rotation) % 360
        img = img.rotate(ccw, expand=True, fillcolor=255)
    return img


__all__ = ["BUILTIN_FONTS", "BuiltinFont", "render_text_image"]
