"""Service-level tests for preview_box."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
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


async def test_preview_box_writes_file_and_returns_path(hass, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    out = tmp_path / "p.txt"
    with patch.object(hass.config, "is_allowed_path", return_value=True):
        result = await hass.services.async_call(
            DOMAIN,
            "preview_box",
            {
                "text": "Hi",
                "style": "ascii",
                "total_width": 10,
                "output_path": str(out),
            },
            blocking=True,
            return_response=True,
        )
    assert result is not None
    assert result["path"] == str(out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert lines[0] == "+--------+"
    assert lines[1] == "|Hi      |"
    assert result["line_count"] == 3
    assert result["width"] == 10


async def test_preview_box_default_path_under_tmpdir(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    result = await hass.services.async_call(
        DOMAIN,
        "preview_box",
        {"text": "Hi", "style": "ascii", "total_width": 8},
        blocking=True,
        return_response=True,
    )
    assert result is not None
    p = Path(result["path"])
    assert p.exists()
    assert "escpos_preview_box" in p.name
    p.unlink()


async def test_preview_box_rejects_output_path_outside_tempdir(hass) -> None:  # type: ignore[no-untyped-def]
    """S-M5: user-supplied output_path must be inside the system tempdir.

    Otherwise a non-admin HA user could call preview_box with
    output_path=/config/configuration.yaml and clobber it with text.
    """
    from homeassistant.exceptions import HomeAssistantError
    import pytest

    await _setup_entry(hass)
    with pytest.raises(HomeAssistantError, match="temp directory"):
        await hass.services.async_call(
            DOMAIN,
            "preview_box",
            {
                "text": "Hi",
                "output_path": "/etc/forbidden.txt",
            },
            blocking=True,
            return_response=True,
        )


async def test_preview_box_default_filename_does_not_leak_entry_id(hass) -> None:  # type: ignore[no-untyped-def]
    """Default /tmp filename uses a hashed token, not the raw HA entry_id.

    Regression for the previous behaviour where any local user could
    enumerate which integration entries existed by listing /tmp.
    """
    entry = await _setup_entry(hass)
    result = await hass.services.async_call(
        DOMAIN,
        "preview_box",
        {"text": "Hi", "style": "ascii", "total_width": 8},
        blocking=True,
        return_response=True,
    )
    assert result is not None
    p = Path(result["path"])
    try:
        assert entry.entry_id not in p.name, (
            f"raw entry_id {entry.entry_id!r} leaked into filename {p.name!r}"
        )
        # The hashed token is 16 hex chars and stable per entry.
        assert "escpos_preview_box_" in p.name
    finally:
        if p.exists():
            p.unlink()


async def test_preview_box_rejects_multiple_targets(hass) -> None:  # type: ignore[no-untyped-def]
    """preview_box returns a single response shape — refuse ambiguous multi-target calls."""
    from homeassistant.exceptions import HomeAssistantError
    import pytest

    await _setup_entry(hass)
    # Add a second entry so device_id=[...] with two ids resolves to >1 entry.
    second = MockConfigEntry(
        domain=DOMAIN,
        title="5.6.7.8:9100",
        data={CONF_HOST: "5.6.7.8", CONF_PORT: 9100},
        unique_id="5.6.7.8:9100",
    )
    second.add_to_hass(hass)
    with patch("escpos.printer.Network"):
        assert await hass.config_entries.async_setup(second.entry_id)
        await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError, match="exactly one printer target"):
        await hass.services.async_call(
            DOMAIN,
            "preview_box",
            {"text": "Hi", "style": "ascii", "total_width": 8},
            blocking=True,
            return_response=True,
        )
