from unittest.mock import MagicMock, patch

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


def _get_set_kwargs(fake_printer: MagicMock) -> dict:
    """Extract kwargs from the printer.set() call."""
    fake_printer.set.assert_called_once()
    return fake_printer.set.call_args.kwargs


async def test_print_text_service(hass):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Hello"},
            blocking=True,
        )
    assert fake.text.called


async def test_print_text_double_width_height(hass):  # type: ignore[no-untyped-def]
    """Test that width/height 'double' passes custom_size=True to printer.set()."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Big text", "width": "double", "height": "double"},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    assert kw["width"] == 2
    assert kw["height"] == 2
    assert kw["custom_size"] is True
    assert kw["normal_textsize"] is False


async def test_print_text_normal_size(hass):  # type: ignore[no-untyped-def]
    """Test that normal width/height passes normal_textsize=True, custom_size=False."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Normal text"},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    assert kw["custom_size"] is False
    assert kw["normal_textsize"] is True


async def test_print_text_triple_width_normal_height(hass):  # type: ignore[no-untyped-def]
    """Test mixed sizes: triple width, normal height still triggers custom_size."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Wide text", "width": "triple", "height": "normal"},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    assert kw["width"] == 3
    assert kw["height"] == 1
    assert kw["custom_size"] is True
    assert kw["normal_textsize"] is False


async def test_print_text_numeric_width_height(hass):  # type: ignore[no-untyped-def]
    """Test numeric width/height values pass through print_text service end-to-end."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "Numeric size", "width": 4, "height": 6},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    assert kw["width"] == 4
    assert kw["height"] == 6
    assert kw["custom_size"] is True
    assert kw["normal_textsize"] is False


async def test_print_qr_resets_text_size(hass):  # type: ignore[no-untyped-def]
    """Test that print_qr sends normal_textsize=True to reset text size state."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_qr",
            {"data": "https://example.com"},
            blocking=True,
        )
    fake.set.assert_called_once()
    kw = fake.set.call_args.kwargs
    assert kw.get("normal_textsize") is True
    # A prior print_text(invert=True) must not leak into the QR: escpos set()
    # skips unpassed params, so this path must send invert=False explicitly.
    assert kw.get("invert") is False


async def test_print_text_invert_density_font(hass):  # type: ignore[no-untyped-def]
    """Test that invert/density/font pass through print_text to printer.set()."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "hello", "invert": True, "density": 4, "font": "B"},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    assert kw["invert"] is True
    assert kw["density"] == 4
    assert kw["font"] == "b"  # schema lowercases


async def test_print_text_styling_defaults_reset_sticky_state(hass):  # type: ignore[no-untyped-def]
    """Test that invert/font are always sent concretely; density stays unset."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text",
            {"text": "hello"},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    # invert/font always sent concretely so a prior job can't leak state;
    # density omitted -> None -> escpos sends nothing (sticky by design).
    assert kw["invert"] is False
    assert kw["font"] == "a"
    assert kw["density"] is None


async def test_print_text_utf8_invert_density_font(hass):  # type: ignore[no-untyped-def]
    """Test that invert/density/font pass through print_text_utf8 to printer.set()."""
    await _setup_entry(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_text_utf8",
            {"text": "hello", "invert": True, "density": 4, "font": "B"},
            blocking=True,
        )
    kw = _get_set_kwargs(fake)
    assert kw["invert"] is True
    assert kw["density"] == 4
    assert kw["font"] == "b"  # schema lowercases
