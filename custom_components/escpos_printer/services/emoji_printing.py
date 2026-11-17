"""Print text that contains emoji: plain lines natively, emoji lines as images.

ESC/POS codepages have no emoji, so a line with one is rendered to a small
bitmap (see :func:`..text_effects.render_text_image`, which falls back to the
bundled Noto Emoji font) while every other line is still sent as fast native
text. All parts travel over a single connection so they print in order and
nothing can interleave.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import partial
from io import BytesIO
from typing import TYPE_CHECKING, Any

from ..const import EMOJI_MODE_AUTO, EMOJI_MODE_OFF, EMOJI_MODE_STRIP
from ..printer.image_processor import FALLBACK_PROFILE_WIDTH
from ..printer.mapping_utils import map_multiplier
from ..text_effects import render_text_image
from ..text_utils import contains_emoji, strip_emoji, transcode_to_codepage

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

# Pixel size at which the bundled monospace font matches the printer's native
# Font A (12 px wide cells) and Font B (9 px wide cells).
_FONT_SIZE_A = 20
_FONT_SIZE_B = 15
_MAX_FONT_SIZE = 160


@dataclass(frozen=True, slots=True)
class TextPart:
    """Consecutive lines that are printed the same way."""

    text: str
    emoji: bool


def split_into_parts(text: str) -> list[TextPart]:
    """Group the lines of ``text`` into runs with and without emoji.

    Line breaks stay attached to the text parts, so printing the parts in
    order reproduces the original layout; image parts end their own line.
    """
    parts: list[TextPart] = []
    lines = text.split("\n")
    for index, line in enumerate(lines):
        has_emoji = contains_emoji(line)
        last = index == len(lines) - 1
        if has_emoji:
            if parts and parts[-1].emoji:
                parts[-1] = TextPart(f"{parts[-1].text}\n{line}", emoji=True)
            else:
                parts.append(TextPart(line, emoji=True))
            continue
        chunk = line if last else f"{line}\n"
        if parts and not parts[-1].emoji:
            parts[-1] = TextPart(parts[-1].text + chunk, emoji=False)
        elif chunk:
            parts.append(TextPart(chunk, emoji=False))
    return parts


def plan_parts(text: str, mode: str) -> tuple[str, list[TextPart] | None]:
    """Decide how to print ``text`` under the given emoji ``mode``.

    Returns ``(text, parts)``. ``parts`` is ``None`` when the ordinary
    single-call text path is enough (no emoji, or ``off``); ``text`` is the
    possibly emoji-stripped text for that path.
    """
    if mode == EMOJI_MODE_OFF:
        return text, None
    if mode == EMOJI_MODE_STRIP:
        return strip_emoji(text), None
    if mode == EMOJI_MODE_AUTO and contains_emoji(text):
        return text, split_into_parts(text)
    return text, None


def _render_emoji_png(
    text: str, *, font_size: int, max_width_px: int, align: str, font_name: str
) -> bytes:
    """Render one emoji part to PNG bytes. Blocking — call on the executor."""
    image = render_text_image(
        text,
        font_name=font_name,
        font_size=font_size,
        max_width_px=max_width_px,
        align=align,
    )
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _emoji_font_size(text_kwargs: dict[str, Any]) -> int:
    """Pixel size matching the requested native font and size multiplier."""
    base = _FONT_SIZE_B if text_kwargs.get("font") == "b" else _FONT_SIZE_A
    multiplier = max(
        map_multiplier(text_kwargs.get("width")), map_multiplier(text_kwargs.get("height"))
    )
    return min(base * multiplier, _MAX_FONT_SIZE)


async def print_parts(
    hass: HomeAssistant,
    adapter: Any,
    parts: list[TextPart],
    *,
    codepage: str,
    text_kwargs: dict[str, Any],
    cut: str | None,
    feed: int | None,
) -> None:
    """Print ``parts`` in order over one connection, then feed and cut.

    Text parts are transcoded to ``codepage`` and printed natively with
    ``text_kwargs`` (alignment, bold, size, ...). Emoji parts honour the
    alignment, the font (A/B) and the size multiplier; bold, underline and
    invert don't apply to the rendered bitmaps.
    """
    align = text_kwargs.get("align") or "left"
    max_width_px = int(adapter.get_profile_pixel_width(hass) or FALLBACK_PROFILE_WIDTH)
    font_size = _emoji_font_size(text_kwargs)

    async with adapter.batch_connection(hass) as page:
        for part in parts:
            if not part.emoji:
                text = await hass.async_add_executor_job(transcode_to_codepage, part.text, codepage)
                await page.print_text(**{**text_kwargs, "text": text, "encoding": None})
                continue
            png = await hass.async_add_executor_job(
                partial(
                    _render_emoji_png,
                    part.text,
                    font_size=font_size,
                    max_width_px=max_width_px,
                    align=align,
                    font_name="dejavu_mono",
                )
            )
            data_uri = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            await page.print_image(image=data_uri)
        await page.cut_and_feed(cut, feed)


__all__ = [
    "EMOJI_MODE_AUTO",
    "TextPart",
    "plan_parts",
    "print_parts",
    "split_into_parts",
]
