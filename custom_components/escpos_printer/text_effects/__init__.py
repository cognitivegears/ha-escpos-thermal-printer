"""Text-effects subpackage: boxes, multi-column tables, and font/rotation rendering.

The modules here are pure-Python and side-effect-free so they can be unit
tested without HA or a real printer:

- :mod:`borders` — glyph tables and codepage compatibility detection.
- :mod:`box` — text wrapped in a single/double/ASCII border.
- :mod:`table` — multi-column rows with optional borders.
- :mod:`font_render` — render Unicode text to a PIL image with a bundled
  or user-supplied TTF/OTF font; supports 0/90/180/270 rotation.

Service handlers in :mod:`..services.print_handlers` compose these modules
with the existing :meth:`..printer.print_operations.PrintOperationsMixin.print_text`
(boxes/tables) and :meth:`..printer.image_operations.ImageOperationsMixin.print_image`
(font_render → PNG → image pipeline) entry points.
"""

from __future__ import annotations

from .borders import (
    BOX_STYLES,
    BorderGlyphs,
    BorderStyle,
    codepage_supports_box_drawing,
    glyphs_for,
    resolve_style,
)
from .box import render_box
from .font_render import (
    BUILTIN_FONTS,
    BuiltinFont,
    render_text_image,
)
from .table import render_table

__all__ = [
    "BOX_STYLES",
    "BUILTIN_FONTS",
    "BorderGlyphs",
    "BorderStyle",
    "BuiltinFont",
    "codepage_supports_box_drawing",
    "glyphs_for",
    "render_box",
    "render_table",
    "render_text_image",
    "resolve_style",
]
