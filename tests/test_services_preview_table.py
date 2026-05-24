"""Service-level tests for preview_table."""

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


async def test_preview_table_writes_file_and_returns_metadata(hass, tmp_path) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    out = tmp_path / "t.txt"
    with patch.object(hass.config, "is_allowed_path", return_value=True):
        result = await hass.services.async_call(
            DOMAIN,
            "preview_table",
            {
                "rows": [["A", "B"], ["C", "D"]],
                "style": "ascii",
                "total_width": 11,
                "output_path": str(out),
            },
            blocking=True,
            return_response=True,
        )
    assert result is not None
    assert result["path"] == str(out)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    # Mirror tests/text_effects/test_table.py::test_render_table_basic_ascii.
    assert content == "+----+----+\n|A   |B   |\n|C   |D   |\n+----+----+"
    assert result["line_count"] == 4
    assert result["width"] == 11


async def test_preview_table_rejects_output_path_outside_tempdir(hass) -> None:  # type: ignore[no-untyped-def]
    """S-M5/T-H2: user-supplied output_path must be inside the system tempdir.

    Otherwise a non-admin HA user could call preview_table with
    output_path=/config/configuration.yaml and clobber it with text.
    Mirrors the equivalent ``test_preview_box_rejects_output_path_outside_tempdir``.
    """
    from homeassistant.exceptions import HomeAssistantError
    import pytest

    await _setup_entry(hass)
    with pytest.raises(HomeAssistantError, match="temp directory"):
        await hass.services.async_call(
            DOMAIN,
            "preview_table",
            {
                "rows": [["A", "B"]],
                "output_path": "/etc/forbidden.txt",
            },
            blocking=True,
            return_response=True,
        )


async def test_preview_table_default_path_under_tmpdir(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    result = await hass.services.async_call(
        DOMAIN,
        "preview_table",
        {"rows": [["A", "B"]], "style": "ascii", "total_width": 11},
        blocking=True,
        return_response=True,
    )
    assert result is not None
    p = Path(result["path"])
    assert p.exists()
    assert "escpos_preview_table" in p.name
    p.unlink()
