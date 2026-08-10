"""Tests for calibration wizard pattern/sample/share-link helpers."""

import base64
import io
from urllib.parse import parse_qs, urlparse

from PIL import Image

from custom_components.escpos_printer._config_flow.calibration import (
    CODEPAGE_CANDIDATES,
    CODEPAGE_SAMPLE,
    IMPL_CANDIDATES,
    WIDTH_CANDIDATES,
    build_ruler,
    build_share_url,
    checkerboard_data_uri,
    codepage_sample_line,
    width_bar_data_uri,
)


def _decode_data_uri(uri: str) -> Image.Image:
    assert uri.startswith("data:image/png;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    return Image.open(io.BytesIO(raw))


def test_checkerboard_dimensions() -> None:
    img = _decode_data_uri(checkerboard_data_uri())
    assert img.size == (192, 48)


def test_width_candidates_include_832() -> None:
    """The fifth bar (832px) covers wider 100mm/112mm heads."""
    assert WIDTH_CANDIDATES == (384, 512, 576, 640, 832)


def test_width_bar_outline_exact_width_and_label_at_left() -> None:
    for width in WIDTH_CANDIDATES:
        img = _decode_data_uri(width_bar_data_uri(width)).convert("L")
        assert img.size == (width, 28)
        # The border is still black at the far right edge -- clipping
        # there is what a too-narrow printer's bars still detect.
        assert img.getpixel((width - 1, 14)) < 64
        # Interior (away from the border and the label) is mostly white
        # now -- a fraction of the ink (and print-head heat) a solid
        # filled bar would use.
        assert img.getpixel((width // 2, 14)) > 192
        # The label (dark text on white) is still visible in the left 80px.
        # Cropped from x=4 (inside the 3px border) so this actually
        # requires label pixels, not just the border's own left edge.
        left = img.crop((4, 4, 80, 24))
        assert left.getextrema()[0] < 64


def test_ruler_layout() -> None:
    ruler = build_ruler(64)
    assert len(ruler) == 64
    # Tens digits sit at the multiple-of-10 positions (1-based)
    for tens in range(1, 7):
        assert ruler[tens * 10 - 1] == str(tens)


def test_ruler_layout_at_96_cols() -> None:
    """The wizard prints the ruler at 96 cols (its widest supported line_width)."""
    ruler = build_ruler(96)
    assert len(ruler) == 96
    for tens in range(7, 10):
        assert ruler[tens * 10 - 1] == str(tens)


def test_codepage_sample_replaces_unencodable() -> None:
    # CP437 has no €; the sample must show ? instead, never drop the char
    line = codepage_sample_line("CP437")
    assert len(line) == len(CODEPAGE_SAMPLE)
    assert "?" in line
    # CP858 encodes the whole sample
    assert codepage_sample_line("CP858") == CODEPAGE_SAMPLE


def test_candidate_orders() -> None:
    assert IMPL_CANDIDATES[0] == "bitImageRaster"
    assert CODEPAGE_CANDIDATES[0] == "CP858"  # broadest first


def test_share_url_round_trips_non_ascii_model() -> None:
    """A non-ASCII model name must not raise and must round-trip intact
    through the URL-encoded title/body."""
    url = build_share_url(
        "Ünïcödé Prïnter",
        {"profile": "", "integration_version": "1.1.0", "escpos_version": "3.1"},
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert qs["title"] == ["Printer calibration: Ünïcödé Prïnter"]
    assert "Ünïcödé Prïnter" in qs["body"][0]


def test_share_url_contains_everything() -> None:
    url = build_share_url(
        "Rongta RP850P",
        {
            "impl": "bitImageRaster",
            "impls_clean": ["bitImageRaster", "bitImageColumn"],
            "width_pixels": 576,
            "line_width": 48,
            "codepage": "CP858",
            "codepages_match": ["CP858", "CP850"],
            "profile": "",
            "integration_version": "1.1.0",
            "escpos_version": "3.1",
        },
    )
    parsed = urlparse(url)
    assert parsed.netloc == "github.com"
    assert parsed.path == "/cognitivegears/ha-escpos-thermal-printer/issues/new"
    qs = parse_qs(parsed.query)
    assert qs["title"] == ["Printer calibration: Rongta RP850P"]
    body = qs["body"][0]
    for expected in (
        "Rongta RP850P",
        "576",
        "48",
        "CP858",
        "bitImageColumn",
        "bitImageRaster: true",  # draft profile YAML snippet
        "media:",
    ):
        assert expected in body
