"""Service-level tests for print_text_image."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

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


async def test_print_text_image_dispatches_via_image_pipeline(hass) -> None:  # type: ignore[no-untyped-def]
    """print_text_image renders text to PIL then funnels the PNG into adapter.print_image."""
    await _setup_entry(hass)

    # Patch the adapter's print_image so we can inspect the kwargs without
    # actually exercising the dither / slice / send path (which would need
    # a real printer mock plus the full image pipeline).
    with patch(
        "custom_components.escpos_printer.printer.image_operations."
        "ImageOperationsMixin.print_image",
        new_callable=AsyncMock,
    ) as mock_print_image:
        await hass.services.async_call(
            DOMAIN,
            "print_text_image",
            {
                "text": "HEADER",
                "font": "dejavu_sans",
                "font_size": 32,
                "rotation": 0,
            },
            blocking=True,
        )

    mock_print_image.assert_awaited_once()
    kwargs = mock_print_image.await_args.kwargs
    # rotation is forced to 0 downstream; the text canvas is already in
    # its final orientation.
    assert kwargs["rotation"] == 0
    # The source is a base64 data URI of a PNG.
    image_arg = kwargs["image"]
    assert image_arg.startswith("data:image/png;base64,")
    payload = image_arg.removeprefix("data:image/png;base64,")
    raw = base64.b64decode(payload)
    assert raw.startswith(b"\x89PNG")


async def test_print_text_image_rotation_forwarded_to_renderer(hass) -> None:  # type: ignore[no-untyped-def]
    """User-supplied rotation rotates the canvas, then rotation=0 is passed downstream."""
    await _setup_entry(hass)
    with (
        patch(
            "custom_components.escpos_printer.services.print_handlers.render_text_image"
        ) as mock_renderer,
        patch(
            "custom_components.escpos_printer.printer.image_operations."
            "ImageOperationsMixin.print_image",
            new_callable=AsyncMock,
        ) as mock_print_image,
    ):
        # Return a real-looking PIL image so PNG serialisation succeeds.
        from PIL import Image

        mock_renderer.return_value = Image.new("L", (32, 16), 255)
        await hass.services.async_call(
            DOMAIN,
            "print_text_image",
            {"text": "X", "rotation": 90},
            blocking=True,
        )
    # Renderer called with rotation=90.
    assert mock_renderer.call_args.kwargs["rotation"] == 90
    # Downstream image pipeline called with rotation=0.
    assert mock_print_image.await_args.kwargs["rotation"] == 0


async def test_print_text_image_default_font_is_dejavu_mono(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    with (
        patch(
            "custom_components.escpos_printer.services.print_handlers.render_text_image"
        ) as mock_renderer,
        patch(
            "custom_components.escpos_printer.printer.image_operations."
            "ImageOperationsMixin.print_image",
            new_callable=AsyncMock,
        ),
    ):
        from PIL import Image

        mock_renderer.return_value = Image.new("L", (16, 16), 255)
        await hass.services.async_call(
            DOMAIN,
            "print_text_image",
            {"text": "X"},
            blocking=True,
        )
    assert mock_renderer.call_args.kwargs["font_name"] == "dejavu_mono"


async def test_print_text_image_rejects_bad_rotation(hass) -> None:  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    import voluptuous as vol

    with patch("escpos.printer.Network", return_value=MagicMock()):
        try:
            await hass.services.async_call(
                DOMAIN,
                "print_text_image",
                {"text": "X", "rotation": 45},
                blocking=True,
            )
        except vol.Invalid:
            return
        raise AssertionError("expected voluptuous error for invalid rotation")


async def test_print_text_image_accepts_font_under_config_fonts_dir(hass) -> None:  # type: ignore[no-untyped-def]
    """Paths under ``<config>/fonts/`` work without an allowlist entry.

    Regression for the friction point: the most common font-path
    scenario (drop file in /config/fonts/) should not require editing
    ``configuration.yaml``.
    """
    from pathlib import Path

    await _setup_entry(hass)
    fonts_dir = Path(hass.config.path("fonts"))
    fonts_dir.mkdir(parents=True, exist_ok=True)
    bundled = (
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "escpos_printer"
        / "fonts"
        / "DejaVuSansMono.ttf"
    )
    dest = fonts_dir / "TestUser.ttf"
    dest.write_bytes(bundled.read_bytes())

    # Force is_allowed_path to return False so the test asserts the
    # fonts-dir code branch — *not* a coincidental allowlist match.
    with (
        patch.object(hass.config, "is_allowed_path", return_value=False),
        patch(
            "custom_components.escpos_printer.printer.image_operations."
            "ImageOperationsMixin.print_image",
            new_callable=AsyncMock,
        ) as mock_print_image,
    ):
        await hass.services.async_call(
            DOMAIN,
            "print_text_image",
            {"text": "X", "font_path": str(dest)},
            blocking=True,
        )

    mock_print_image.assert_awaited_once()
    dest.unlink()


async def test_print_text_image_rejects_font_outside_trusted_dirs(hass, tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Paths outside ``<config>/fonts/`` still require allowlist."""
    from pathlib import Path

    from homeassistant.exceptions import HomeAssistantError
    import pytest

    await _setup_entry(hass)
    src = (
        Path(__file__).resolve().parent.parent
        / "custom_components"
        / "escpos_printer"
        / "fonts"
        / "DejaVuSansMono.ttf"
    )
    elsewhere = tmp_path / "Other.ttf"
    elsewhere.write_bytes(src.read_bytes())

    with (
        patch.object(hass.config, "is_allowed_path", return_value=False),
        pytest.raises(HomeAssistantError, match="allowlist"),
    ):
        await hass.services.async_call(
            DOMAIN,
            "print_text_image",
            {"text": "X", "font_path": str(elsewhere)},
            blocking=True,
        )
