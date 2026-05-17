import base64
import io
from unittest.mock import MagicMock, patch

from PIL import Image
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup(hass):  # type: ignore[no-untyped-def]
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


async def test_print_image_service_local(hass, tmp_path):  # type: ignore[no-untyped-def]
    img_path = tmp_path / "img.png"
    Image.new("RGB", (10, 10)).save(img_path)
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": str(img_path)},
            blocking=True,
        )
    assert fake.image.called


async def test_print_image_service_base64_data_uri(hass):  # type: ignore[no-untyped-def]
    buf = io.BytesIO()
    Image.new("RGB", (20, 20), color=(0, 0, 0)).save(buf, format="PNG")
    src = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": src},
            blocking=True,
        )
    assert fake.image.called


async def test_print_image_service_template_renders(hass, tmp_path):  # type: ignore[no-untyped-def]
    img_path = tmp_path / "tpl.png"
    Image.new("RGB", (10, 10)).save(img_path)
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": "{{ '" + str(img_path) + "' }}"},
            blocking=True,
        )
    assert fake.image.called


async def test_print_image_service_rotation_passes_through(hass, tmp_path):  # type: ignore[no-untyped-def]
    img_path = tmp_path / "rot.png"
    # 20 wide x 10 tall — after 90 CW rotation should be 10 wide x 20 tall
    Image.new("L", (20, 10), color=200).save(img_path)
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": str(img_path), "rotation": 90},
            blocking=True,
        )
    assert fake.image.called
    # The PIL image handed to printer.image() should have rotated dimensions.
    sent = fake.image.call_args.args[0]
    assert sent.width == 10
    assert sent.height == 20


async def test_print_image_url_service_dispatches(hass, tmp_path):  # type: ignore[no-untyped-def]
    """The print_image_url convenience service should dispatch to print_image."""
    await _setup(hass)
    # We don't actually fetch — patch resolve_image_bytes to short-circuit.
    fake_bytes = io.BytesIO()
    Image.new("L", (10, 10), color=128).save(fake_bytes, format="PNG")
    raw = fake_bytes.getvalue()

    fake = MagicMock()
    with (
        patch("escpos.printer.Network", return_value=fake),
        patch(
            "custom_components.escpos_printer.printer.image_operations"
            ".resolve_image_bytes",
            return_value=(raw, "image/png"),
        ),
    ):
        await hass.services.async_call(
            DOMAIN,
            "print_image_url",
            {"url": "https://example.com/x.png"},
            blocking=True,
        )
    assert fake.image.called


async def test_print_image_path_service_dispatches(hass, tmp_path):  # type: ignore[no-untyped-def]
    """print_image_path should accept a local file path and route to the same backend."""
    img_path = tmp_path / "from_path.png"
    Image.new("RGB", (10, 10)).save(img_path)
    # Allowlist tmp_path so the path resolver accepts it.
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image_path",
            {"path": str(img_path)},
            blocking=True,
        )
    assert fake.image.called


async def test_print_image_path_passes_rotation_and_mirror_through(hass, tmp_path):  # type: ignore[no-untyped-def]
    """Confirm rotation + mirror on print_image_path actually transform pixels.

    Source is a 20x10 image with a single bright pixel near the top-left
    (column 2). After 90° clockwise rotation it becomes 10x20 with the
    bright pixel near the top-right; after also mirroring it flips back
    to the top-left in the rotated frame. We assert both the output
    dimensions and the position of the bright pixel to prove the
    options are not silently ignored.
    """
    img_path = tmp_path / "rot.png"
    src = Image.new("L", (20, 10), color=0)
    # Bright marker in the source at column 2, row 1.
    src.putpixel((2, 1), 255)
    src.save(img_path)
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image_path",
            {
                "path": str(img_path),
                "rotation": 90,
                "mirror": True,
                # Force a known dither path so the marker survives.
                "dither": "threshold",
                "threshold": 128,
            },
            blocking=True,
        )
    assert fake.image.called
    sent = fake.image.call_args.args[0]
    # 20x10 rotated 90 CW becomes 10x20.
    assert sent.width == 10
    assert sent.height == 20
    # Find the position of the surviving bright pixel(s) in the 1-bit
    # result. Source (2, 1) → after rotate-90-CW → (8, 2); after mirror
    # (horizontal flip) → (1, 2). Mode "1" stores 0/255 — find any white
    # pixel and assert it lands where the rotation+mirror dictates.
    one_bit = sent.convert("1")
    white_pixels = [
        (x, y)
        for y in range(one_bit.height)
        for x in range(one_bit.width)
        if one_bit.getpixel((x, y))
    ]
    assert (1, 2) in white_pixels, (
        f"mirror+rotation produced wrong pixel layout; white pixels: {white_pixels}"
    )


async def test_print_image_legacy_literal_path_with_inline_options(hass, tmp_path):  # type: ignore[no-untyped-def]
    """Backwards-compat: literal-path automations with image-options keep working.

    Beyond the bare-string case already covered by ``test_print_image_service_local``,
    real-world legacy automations also passed options alongside the literal path
    (``image: /config/x.png`` + ``rotation: 90``). The selector swap from
    ``text:`` to ``template:`` must preserve that calling shape — the template
    editor accepts plain strings AND surrounding option keys validate the same
    way they did before.
    """
    img_path = tmp_path / "legacy.png"
    Image.new("L", (10, 20), color=0).save(img_path)
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {
                # Literal path, no Jinja braces.
                "image": str(img_path),
                "rotation": 90,
                "mirror": True,
                "high_density": False,
            },
            blocking=True,
        )
    assert fake.image.called
    sent = fake.image.call_args.args[0]
    # 10x20 rotated 90 CW becomes 20x10.
    assert sent.width == 20
    assert sent.height == 10
    # Verify the override actually reached the printer call site.
    kwargs = fake.image.call_args.kwargs
    assert kwargs.get("high_density_vertical") is False
    assert kwargs.get("high_density_horizontal") is False


async def test_preview_image_writes_png_and_returns_path(hass, tmp_path):  # type: ignore[no-untyped-def]
    """preview_image runs the pipeline and saves the result without printing."""
    img_path = tmp_path / "src.png"
    Image.new("L", (40, 40), color=128).save(img_path)
    out_path = tmp_path / "preview.png"
    # Add tmp_path to allowlist so the output write succeeds.
    hass.config.allowlist_external_dirs = {str(tmp_path)}
    await _setup(hass)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        result = await hass.services.async_call(
            DOMAIN,
            "preview_image",
            {"image": str(img_path), "output_path": str(out_path)},
            blocking=True,
            return_response=True,
        )
    # Service response is dict; HA wraps it per-entry in some versions.
    assert isinstance(result, dict)
    # Don't print — only preview should call image() zero times.
    assert not fake.image.called
    # File exists with a real PNG payload.
    assert out_path.exists()
    saved = Image.open(out_path)
    assert saved.mode == "1"
