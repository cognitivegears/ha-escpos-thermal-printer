"""Tests for print_qr's opt-in native rendering (python-escpos qr(native=True))."""

from __future__ import annotations

import sys
from typing import Any
from unittest.mock import MagicMock, patch

# Captured at import time (before conftest's autouse fixture swaps in the
# fake escpos package) so the native path can build real GS ( k bytes.
from escpos.printer import Dummy as _RealDummy
from homeassistant.const import CONF_HOST, CONF_PORT
import probatio as vol
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import CONF_PROFILE, DOMAIN
from custom_components.escpos_printer.services.schemas import PRINT_QR_SCHEMA

# GS ( k -- the ESC/POS 2D-code function python-escpos uses for native QR.
_GS_PAREN_K = b"\x1d(k"


async def _setup_entry(hass: Any, profile: str | None = None) -> MockConfigEntry:
    data: dict[str, Any] = {CONF_HOST: "1.2.3.4", CONF_PORT: 9100}
    if profile:
        data[CONF_PROFILE] = profile
    entry = MockConfigEntry(
        domain=DOMAIN, title="1.2.3.4:9100", data=data, unique_id="1.2.3.4:9100"
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


@pytest.fixture(autouse=True)
def _real_dummy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys.modules["escpos.printer"], "Dummy", _RealDummy, raising=False)


def _raw_payloads(fake: MagicMock) -> list[bytes]:
    return [c.args[0] for c in fake._raw.call_args_list]


def test_print_qr_schema_native_defaults_false() -> None:
    assert PRINT_QR_SCHEMA({"data": "x"})["native"] is False
    assert PRINT_QR_SCHEMA({"data": "x", "native": True})["native"] is True
    with pytest.raises(vol.Invalid):
        PRINT_QR_SCHEMA({"data": "x", "native": "sometimes"})


async def test_print_qr_default_uses_image_path(hass: Any) -> None:
    """Default behaviour is unchanged: python-escpos qr() without native."""
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(DOMAIN, "print_qr", {"data": "hello"}, blocking=True)
    fake.qr.assert_called_once()
    assert "native" not in fake.qr.call_args.kwargs
    assert not any(p.startswith(_GS_PAREN_K) for p in _raw_payloads(fake))


async def test_print_qr_native_sends_gs_k_in_one_write(hass: Any) -> None:
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_qr",
            {"data": "hello", "native": True, "size": 6, "ec": "H", "align": "center"},
            blocking=True,
        )
    fake.qr.assert_not_called()
    payloads = [p for p in _raw_payloads(fake) if p.startswith(_GS_PAREN_K)]
    assert len(payloads) == 1
    payload = payloads[0]
    assert b"hello" in payload
    # Module size 6 and error correction H (48 + 3) are encoded in the command.
    assert _GS_PAREN_K + b"\x03\x001C\x06" in payload
    assert _GS_PAREN_K + b"\x03\x001E3" in payload
    # Alignment still goes through set(), as on the image path.
    assert fake.set.call_args.kwargs["align"] == "center"


async def test_print_qr_native_falls_back_when_profile_lacks_qr(hass: Any) -> None:
    """A profile declaring qrCode: false prints the image instead."""
    await _setup_entry(hass, profile="TM-U220")
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN, "print_qr", {"data": "hello", "native": True}, blocking=True
        )
    fake.qr.assert_called_once()
    assert not any(p.startswith(_GS_PAREN_K) for p in _raw_payloads(fake))


async def test_print_qr_native_falls_back_when_build_raises(hass: Any, caplog: Any) -> None:
    """A python-escpos error while building the command sends nothing native."""
    await _setup_entry(hass)
    fake = MagicMock()
    with (
        patch("escpos.printer.Network", return_value=fake),
        patch("escpos.printer.Dummy.qr", side_effect=ValueError("unsupported")),
    ):
        await hass.services.async_call(
            DOMAIN, "print_qr", {"data": "hello", "native": True}, blocking=True
        )
    fake.qr.assert_called_once()
    assert not any(p.startswith(_GS_PAREN_K) for p in _raw_payloads(fake))
    assert "falling back to image rendering" in caplog.text


async def test_print_qr_native_transport_failure_is_not_retried_as_image(hass: Any) -> None:
    """Once the native bytes hit the wire, a write failure propagates (no double print)."""
    await _setup_entry(hass)
    fake = MagicMock()

    def _raw(payload: bytes) -> None:
        if payload.startswith(_GS_PAREN_K):
            raise OSError("connection reset")

    fake._raw.side_effect = _raw
    with (
        patch("escpos.printer.Network", return_value=fake),
        pytest.raises(Exception, match="connection reset"),
    ):
        await hass.services.async_call(
            DOMAIN, "print_qr", {"data": "hello", "native": True}, blocking=True
        )
    fake.qr.assert_not_called()
