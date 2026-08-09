"""Tests for the newly-exposed hardware barcode types.

NW7, GS1-128, and the four GS1 DataBar variants are valid python-escpos
``BARCODE_TYPES`` entries but were missing from the ``print_barcode``
selector and the ``security.validate_barcode_data`` allowlist.
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

# Imported at module (collection) time, before the autouse fake_escpos_module
# fixture swaps sys.modules["escpos.escpos"] for a fake — same trick as the
# real-Dummy imports in test_cut_feed_before_cut.py.
from escpos.escpos import HW_BARCODE_NAMES, SW_BARCODE_NAMES
from homeassistant.const import CONF_HOST, CONF_PORT
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

from custom_components.escpos_printer.const import DOMAIN
from custom_components.escpos_printer.security import validate_barcode_data


async def _setup_entry(hass) -> MockConfigEntry:  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize(
    "bc_type",
    [
        "NW7",
        "GS1-128",
        "GS1 DATABAR OMNIDIRECTIONAL",
        "GS1 DATABAR TRUNCATED",
        "GS1 DATABAR LIMITED",
        "GS1 DATABAR EXPANDED",
    ],
)
def test_validate_barcode_data_accepts_new_types_without_warning(
    bc_type: str, caplog: pytest.LogCaptureFixture
) -> None:
    """These types must not hit the "Unknown barcode type" warning branch."""
    _, canonical = validate_barcode_data("123456", bc_type)
    assert "Unknown barcode type" not in caplog.text
    assert canonical in (bc_type, "CODABAR")  # NW7 aliases to CODABAR


@pytest.mark.parametrize(
    "bc_type",
    [
        "NW7",
        "GS1-128",
        "GS1 DATABAR OMNIDIRECTIONAL",
        "GS1 DATABAR TRUNCATED",
        "GS1 DATABAR LIMITED",
        "GS1 DATABAR EXPANDED",
    ],
)
async def test_print_barcode_service_accepts_new_types(hass, bc_type: str):  # type: ignore[no-untyped-def]
    """The print_barcode service schema must accept the new selector options."""
    entry = await _setup_entry(hass)
    adapter = entry.runtime_data.adapter

    with patch.object(adapter, "print_barcode", AsyncMock()) as mock_print:
        await hass.services.async_call(
            DOMAIN,
            "print_barcode",
            {"code": "123456", "bc": bc_type},
            blocking=True,
        )
    assert mock_print.call_args.kwargs["bc"] == bc_type


def test_every_selector_type_resolves_in_python_escpos() -> None:
    """Every type offered in the services.yaml selector must canonicalize to a
    name python-escpos can resolve (hardware or software renderer).

    Regression guard for ITF14, which sat in the selector and allowlist but had
    no alias and no entry in the library's name maps, so every print raised
    BarcodeTypeError.
    """
    services = yaml.safe_load(
        (
            Path(__file__).parent.parent / "custom_components" / "escpos_printer" / "services.yaml"
        ).read_text()
    )
    options = services["print_barcode"]["fields"]["bc"]["selector"]["select"]["options"]
    assert options, "selector options missing"

    for option in options:
        _, canonical = validate_barcode_data("1234567890", option)
        key = "".join(ch for ch in canonical.upper() if ch.isalnum())
        assert HW_BARCODE_NAMES.get(key) or SW_BARCODE_NAMES.get(key), (
            f"{option!r} canonicalizes to {canonical!r}, which python-escpos "
            "cannot resolve to a hardware or software barcode type"
        )
