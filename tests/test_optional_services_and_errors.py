from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={"host": "1.2.3.4", "port": 9100},
        unique_id="1.2.3.4:9100",
    )
    entry.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry


async def test_print_image_url_download_error(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)

    fake = MagicMock()

    # S-H1: the production fetch builds its own session via
    # ``_build_pinned_session``. Stub the session-factory directly so
    # ``session.get(...)`` raises a ClientError without going through a
    # real socket (or leaving an un-awaited AsyncMock coroutine behind).
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=None)

    def _get(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise aiohttp.ClientError("download failed")

    session.get = _get
    from custom_components.escpos_printer import image_sources

    def _fake_build(_hostname: str, _addrs: list[str]):  # type: ignore[no-untyped-def]
        return session

    with (
        patch("escpos.printer.Network", return_value=fake),
        patch.object(image_sources, "_build_pinned_session", _fake_build),
        patch(
            "custom_components.escpos_printer.security._resolve_hostname_sync",
            return_value=["93.184.216.34"],
        ),
    ):
        with pytest.raises(Exception):
            await hass.services.async_call(
                DOMAIN,
                "print_image",
                {"image": "https://example.com/img.png"},
                blocking=True,
            )
    assert any("Downloading image from URL" in rec.message for rec in caplog.records)


async def test_encoding_codepage_warning(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    # Cause _set_codepage to raise
    fake._set_codepage.side_effect = RuntimeError("bad codepage")
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello", "encoding": "XYZ"},
            blocking=True,
        )
    assert any("Unsupported encoding/codepage" in rec.message for rec in caplog.records)


async def test_print_barcode_service_calls_escpos(hass):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_barcode",
            {"code": "4006381333931", "bc": "EAN13", "height": 80, "width": 3},
            blocking=True,
        )
    fake.barcode.assert_called()


async def test_beep_service_logs_when_unsupported(hass, caplog):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    fake = MagicMock()
    # Simulate unsupported buzzer by raising AttributeError
    fake.buzzer.side_effect = AttributeError()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(DOMAIN, "beep", {"times": 2, "duration": 3}, blocking=True)
    # Should warn if not supported
    assert any("does not support buzzer" in rec.message for rec in caplog.records)
