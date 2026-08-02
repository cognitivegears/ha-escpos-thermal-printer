"""Tests for the standalone ``cut`` service's ``feed_before_cut`` option.

python-escpos's ``cut(mode=..., feed=True)`` force-feeds ~6 lines before
cutting when ``feed=True`` (its own default). ``feed_before_cut`` exposes
that knob on the standalone cut service only.

python-escpos's own ``cut(feed=False)`` ignores ``mode`` and always emits
the partial-cut opcode (``GS V 66 0`` / ``b"\\x1dVB\\x00"``) -- verified
below via ``Dummy``. The ``feed_before_cut=False`` path therefore bypasses
``cut()`` and emits the ESC/POS function-B opcode directly so ``mode`` is
respected: ``GS V 65 0`` (``b"\\x1dVA\\x00"``) for full, ``GS V 66 0`` for
partial.
"""

from unittest.mock import MagicMock, patch

from escpos.printer import Dummy
from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN

FULL_CUT_NO_FEED = b"\x1dVA\x00"
PARTIAL_CUT_NO_FEED = b"\x1dVB\x00"


def test_python_escpos_cut_feed_false_ignores_mode() -> None:
    """Document the upstream bug this fix works around.

    python-escpos's ``Escpos.cut(mode=..., feed=False)`` always emits the
    partial-cut opcode regardless of ``mode`` -- this is why the adapter
    can't just pass ``feed_before_cut`` straight through to ``cut()``.
    """
    full = Dummy()
    full.cut(mode="FULL", feed=False)
    part = Dummy()
    part.cut(mode="PART", feed=False)
    assert full.output == part.output == PARTIAL_CUT_NO_FEED


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


async def test_cut_omitted_feed_before_cut_defaults_true(hass):  # type: ignore[no-untyped-def]
    """Omitting feed_before_cut preserves today's behaviour: feed=True."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "cut",
            {"mode": "full"},
            blocking=True,
        )
    fake.cut.assert_called_once_with(mode="FULL", feed=True)


async def test_cut_feed_before_cut_true_passes_through(hass):  # type: ignore[no-untyped-def]
    """feed_before_cut: true (explicit) still reaches python-escpos's cut()."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "cut",
            {"mode": "partial", "feed_before_cut": True},
            blocking=True,
        )
    fake.cut.assert_called_once_with(mode="PART", feed=True)


async def test_cut_feed_before_cut_false_emits_full_cut_bytes(hass):  # type: ignore[no-untyped-def]
    """feed_before_cut: false with mode: full must still emit a full cut."""
    await _setup_entry(hass)

    dummy = Dummy()
    with patch("escpos.printer.Network", return_value=dummy):
        await hass.services.async_call(
            DOMAIN,
            "cut",
            {"mode": "full", "feed_before_cut": False},
            blocking=True,
        )
    assert dummy.output == FULL_CUT_NO_FEED


async def test_cut_feed_before_cut_false_emits_partial_cut_bytes(hass):  # type: ignore[no-untyped-def]
    """feed_before_cut: false with mode: partial emits a partial cut."""
    await _setup_entry(hass)

    dummy = Dummy()
    with patch("escpos.printer.Network", return_value=dummy):
        await hass.services.async_call(
            DOMAIN,
            "cut",
            {"mode": "partial", "feed_before_cut": False},
            blocking=True,
        )
    assert dummy.output == PARTIAL_CUT_NO_FEED
