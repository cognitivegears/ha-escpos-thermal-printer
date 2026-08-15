"""Compose the 'Sample test print' receipt (device page button).

One uninterrupted receipt on a single held connection: logo, boxed
header, styled text, table, separator, QR. ASCII border style on
purpose — it renders identically on every codepage, so the sample
never needs transcoding.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant

from .text_effects.box import render_box
from .text_effects.table import render_table

if TYPE_CHECKING:
    from . import EscposConfigEntry

_LOGO_PATH = Path(__file__).parent / "brand" / "logo.png"
_REPO_URL = "https://github.com/cognitivegears/ha-escpos-thermal-printer"


def _logo_data_uri() -> str:
    """base64 data URI for the bundled logo (blocking; run via executor)."""
    return "data:image/png;base64," + base64.b64encode(_LOGO_PATH.read_bytes()).decode()


async def async_print_sample(hass: HomeAssistant, entry: EscposConfigEntry) -> None:
    """Print the sample receipt on the entry's printer."""
    from . import _shared_print_config  # noqa: PLC0415 (avoid import cycle at module load)

    adapter = entry.runtime_data.adapter
    line_width = _shared_print_config(entry)["line_width"]
    logo = await hass.async_add_executor_job(_logo_data_uri)

    header = render_box(
        f"ESC/POS Sample Print\n{entry.title}",
        inner_width=max(line_width - 2, 10),
        style="ascii",
        align="center",
    )
    table = render_table(
        [["Item", "Qty"], ["Receipt demo", "1"], ["Styled text", "3"]],
        total_width=line_width,
        style="ascii",
        header=True,
    )

    async with adapter.batch_connection(hass) as page:
        await page.print_image(image=logo, auto_resize=True)
        await page.print_text(text=header + "\n")
        await page.print_text(text="Bold text\n", bold=True)
        await page.print_text(text="Underlined text\n", underline="single")
        await page.print_text(text="Double size\n", width=2, height=2)
        await page.print_text(text=table + "\n")
        await page.print_text(text="=" * line_width + "\n")
        await page.print_qr(data=_REPO_URL)
        await page.print_text(text=f"Docs & source:\n{_REPO_URL}\n")
        await page.feed(2)

    # Batch pages never cut (documented _BatchPage contract) — follow-up
    # cut like the calibration wizard does. "none" would make the button
    # print an uncut dangling receipt, so fall back to full.
    cut_mode = entry.runtime_data.defaults.get("cut") or "full"
    if cut_mode == "none":
        cut_mode = "full"
    await adapter.cut(hass, mode=cut_mode)
