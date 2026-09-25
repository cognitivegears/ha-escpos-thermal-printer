"""Tests for calibration wizard pattern/sample/share-link helpers."""

import base64
import io
from urllib.parse import parse_qs, urlparse

from PIL import Image

from custom_components.escpos_printer._config_flow.calibration import (
    CODEPAGE_CANDIDATES,
    CODEPAGE_SAMPLE,
    IMPL_CANDIDATES,
    NOT_QUERIED,
    WIDTH_CANDIDATES,
    _sanitize_identity,
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


def test_width_candidates_include_832_and_546() -> None:
    """832px covers wider 100mm/112mm heads; 546px is the Epson 42-column
    mode class (e.g. TM-T20II in 42-col mode)."""
    assert WIDTH_CANDIDATES == (384, 512, 546, 576, 640, 832)


def test_width_bar_outline_exact_width_with_intact_right_border() -> None:
    for width in WIDTH_CANDIDATES:
        img = _decode_data_uri(width_bar_data_uri(width)).convert("L")
        assert img.size == (width, 24)
        # The whole point of the box: an intact right-side border at
        # x=width-1 is the signal the calibration step asks the user to
        # look for, so if the printer reproduced the box at full width,
        # this column must be black top to bottom (not just one pixel).
        right_edge = [img.getpixel((width - 1, y)) for y in range(24)]
        assert all(v < 64 for v in right_edge), f"right border not intact at {width}px"
        # Interior (away from the border) is mostly white -- a fraction of
        # the ink (and print-head heat) a solid filled bar would use.
        assert img.getpixel((width // 2, 12)) > 192
        # No baked-in label -- the width number now prints as a separate
        # text line above the box (see _print_width_bars).
        assert img.getpixel((8, 8)) > 192


def test_ruler_layout() -> None:
    ruler = build_ruler(64)
    assert len(ruler) == 64
    # Full numbers, right-aligned so the LAST digit sits on the
    # multiple-of-10 position (1-based): "........10........20..."
    for tens in range(10, 61, 10):
        label = str(tens)
        assert ruler[tens - len(label) : tens] == label
    # No pipe noise, and everything else is dots
    assert "|" not in ruler


def test_ruler_layout_at_96_cols() -> None:
    """The wizard prints the ruler at 96 cols (its widest supported line_width)."""
    ruler = build_ruler(96)
    assert len(ruler) == 96
    for tens in range(70, 91, 10):
        label = str(tens)
        assert ruler[tens - len(label) : tens] == label


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


def test_sanitize_identity_strips_backticks_controls_and_caps_length() -> None:
    # Backtick removal: the report body is embedded in markdown (and a
    # ```yaml fence further down), so a raw backtick from an untrusted GS
    # I reply must not survive into it.
    assert _sanitize_identity("Te`st\x07Name") == "TestName"
    assert _sanitize_identity("A" * 100) == "A" * 64
    assert _sanitize_identity(None) == "(unknown)"
    assert _sanitize_identity("") == "(unknown)"
    assert _sanitize_identity("`\x00") == "(unknown)"


def test_share_url_identity_section_network() -> None:
    url = build_share_url(
        "TM-T20II",
        {
            "profile": "TM-T20II",
            "connection_type": "network",
            "suggestion": "TM-T20II",
            "identity_manufacturer": "EPSON",
            "identity_model": "TM-T20II",
            "identity_firmware": "1.05",
        },
    )
    body = parse_qs(urlparse(url).query)["body"][0]
    for expected in (
        "Detected identity:",
        "Connection type: network",
        "Autodetect suggestion: TM-T20II",
        # Printer-supplied text renders as inline code so a crafted GS I
        # reply can't become a rendered GitHub link/@mention/#ref.
        "Detected manufacturer: `EPSON`",
        "Detected model: `TM-T20II`",
        "Firmware version: `1.05`",
    ):
        assert expected in body


def test_share_url_identity_section_usb_omits_firmware_query_value() -> None:
    url = build_share_url(
        "POS-5890",
        {
            "profile": "",
            "connection_type": "usb",
            "suggestion": "POS-5890",
            "identity_manufacturer": "Zijiang",
            "identity_model": "POS-5890",
            "identity_usb_vid_pid": "0416:5011",
            "identity_firmware": NOT_QUERIED,
        },
    )
    body = parse_qs(urlparse(url).query)["body"][0]
    assert "Detected manufacturer: `Zijiang`" in body
    assert "Detected model: `POS-5890`" in body
    assert "USB VID:PID: 0416:5011" in body
    # The NOT_QUERIED sentinel renders plain, not as inline code.
    assert "Firmware version: (not queried)" in body


def test_share_url_identity_section_network_suggestion_none_when_unmatched() -> None:
    """network/usb DO compute a suggestion -- "none" means it came back empty,
    distinct from "n/a" (never computed at all, e.g. bluetooth/serial)."""
    url = build_share_url("Generic", {"profile": "", "connection_type": "network"})
    body = parse_qs(urlparse(url).query)["body"][0]
    assert "Autodetect suggestion: none" in body


def test_share_url_identity_section_defaults_to_unknown_and_none() -> None:
    """No identity keys at all (e.g. serial/unrecognized connection type) -- safe defaults."""
    url = build_share_url("Generic", {"profile": ""})
    body = parse_qs(urlparse(url).query)["body"][0]
    assert "Connection type: (unknown)" in body
    # Never computed for bluetooth/serial/unrecognized types -- "n/a", not
    # "none" (which means "computed, found nothing").
    assert "Autodetect suggestion: n/a" in body
    assert "Firmware version: (not queried)" not in body
    assert "Firmware version: (unknown)" in body
