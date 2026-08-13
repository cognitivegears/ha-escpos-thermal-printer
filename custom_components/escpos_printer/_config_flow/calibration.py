"""Pure helpers for the printer calibration wizard.

Pattern generators, codepage sample lines, and the GitHub share-link
builder. No printer I/O here — the flow steps in calibration_steps.py
do the printing via the adapter's existing pipeline.
"""

from __future__ import annotations

import base64
import io
from urllib.parse import quote

from PIL import Image, ImageDraw

WIDTH_CANDIDATES: tuple[int, ...] = (384, 512, 546, 576, 640, 832)
IMPL_CANDIDATES: tuple[str, ...] = ("bitImageRaster", "bitImageColumn", "graphics")
# Capability order, broadest encoding first: the wizard stores the first
# checked candidate in this order, so ties resolve to the most capable.
# These are the four most-supported Western codepages across the real
# printer profiles in escpos-printer-db (CP437 97%, CP1252 82%, CP858
# 80%, CP850 77% of bundled profiles). ISO_8859-1 was dropped: no
# bundled profile exposes it, so the profile filter removed it anyway.
CODEPAGE_CANDIDATES: tuple[str, ...] = ("CP858", "CP1252", "CP850", "CP437")
CODEPAGE_SAMPLE = "café ñ ü é ß ° €"

_ISSUES_URL = "https://github.com/cognitivegears/ha-escpos-thermal-printer/issues/new"


def _png_data_uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def checkerboard_data_uri() -> str:
    """192x48 checkerboard of 8px squares — garbles visibly on a wrong impl."""
    img = Image.new("1", (192, 48), 1)
    draw = ImageDraw.Draw(img)
    for y in range(0, 48, 8):
        for x in range(0, 192, 8):
            if (x // 8 + y // 8) % 2 == 0:
                draw.rectangle((x, y, x + 7, y + 7), fill=0)
    return _png_data_uri(img)


def width_bar_data_uri(width_px: int) -> str:
    """Outlined rectangle exactly width_px wide, for right-border detection.

    An outline (3px border) rather than a solid fill draws a fraction of
    the ink a filled bar would -- kinder to the print head, which matters
    on battery-powered (Bluetooth) printers. No label inside the box (the
    candidate width is printed as a text line above it, see
    ``_print_width_bars``): the judgment this box exists for is "does the
    right-side border print intact?", not a length comparison between two
    near-equal bars -- comparing 512 vs 576 (an 11% difference) by eye on
    faint thermal ink proved unreliable on real hardware. A too-wide box
    loses its
    border on both clip firmware (truncated) and wrap firmware (shed into
    garbled fragments on the next line) -- either way, no intact border.
    """
    img = Image.new("1", (width_px, 24), 1)
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, width_px - 1, 23), outline=0, width=3)
    return _png_data_uri(img)


def build_ruler(cols: int = 64) -> str:
    """ASCII column ruler with full numbers at the tens positions.

    Each number is right-aligned so its LAST digit sits exactly on the
    multiple of ten (``........10........20...``): the reader takes the
    last complete number on the first printed line and adds one per dot
    after it — no "4 means 40" decoding, no pipe noise. Hardware-wrapped
    remainder lines carry the later numbers and are ignorable.
    """
    chars = ["."] * cols
    for tens in range(10, cols + 1, 10):
        label = str(tens)
        for offset, digit in enumerate(label):
            chars[tens - len(label) + offset] = digit
    return "".join(chars)


def codepage_sample_line(encoding: str) -> str:
    """The sample round-tripped through ``encoding``; unencodable chars -> '?'."""
    return CODEPAGE_SAMPLE.encode(encoding, errors="replace").decode(encoding)


def build_share_url(model: str, results: dict[str, object]) -> str:
    """Prefilled GitHub new-issue URL with the full measured dataset."""
    impls_raw = results.get("impls_clean")
    impls: list[object] = impls_raw if isinstance(impls_raw, list) else []
    codepages_raw = results.get("codepages_match")
    codepages: list[object] = codepages_raw if isinstance(codepages_raw, list) else []
    feature_lines = "\n".join(
        f"    {impl}: {'true' if impl in impls else 'false'}" for impl in IMPL_CANDIDATES
    )
    body = (
        f"Printer model: {model}\n"
        f"Configured profile: {results.get('profile') or '(generic)'}\n\n"
        f"Calibration results:\n"
        f"- Image implementation stored: {results.get('impl') or '(unchanged)'}\n"
        f"- Implementations that printed cleanly: {', '.join(map(str, impls)) or 'none'}\n"
        f"- Printable width: {results.get('width_pixels') or '(unchanged)'} px\n"
        f"- Columns (font A): {results.get('line_width') or '(unchanged)'}\n"
        f"- Codepage stored: {results.get('codepage') or '(unchanged)'}\n"
        f"- Codepages that matched: {', '.join(map(str, codepages)) or '(step skipped)'}\n\n"
        f"Versions: integration {results.get('integration_version', '?')}, "
        f"python-escpos {results.get('escpos_version', '?')}\n\n"
        f"Draft escpos-printer-db profile:\n\n"
        f"```yaml\n"
        f"{model}:\n"
        f"  name: {model}\n"
        f"  notes: Hardware-verified via HA calibration wizard\n"
        f"  media:\n"
        f"    width:\n"
        f"      pixels: {results.get('width_pixels') or 'null'}\n"
        f"  features:\n"
        f"{feature_lines}\n"
        f"```\n"
    )
    title = f"Printer calibration: {model}"
    return f"{_ISSUES_URL}?title={quote(title)}&body={quote(body)}"
