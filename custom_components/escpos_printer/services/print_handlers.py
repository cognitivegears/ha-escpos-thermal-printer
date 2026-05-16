"""Print operation service handlers."""

from __future__ import annotations

import logging

from homeassistant.core import ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    ATTR_ALIGN,
    ATTR_ALIGN_CT,
    ATTR_BARCODE_HEIGHT,
    ATTR_BARCODE_WIDTH,
    ATTR_BC,
    ATTR_BOLD,
    ATTR_CHECK,
    ATTR_CODE,
    ATTR_CUT,
    ATTR_DATA,
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FEED,
    ATTR_FONT,
    ATTR_FORCE_SOFTWARE,
    ATTR_HEIGHT,
    ATTR_IMAGE,
    ATTR_POS,
    ATTR_SIZE,
    ATTR_TEXT,
    ATTR_UNDERLINE,
    ATTR_WIDTH,
)
from ..image_sources import extract_image_kwargs, render_template
from ..security import sanitize_log_message
from ..text_utils import transcode_to_codepage
from .target_resolution import _async_get_target_entries, _get_adapter_and_defaults

_LOGGER = logging.getLogger(__name__)


def _wrap_unexpected(err: Exception, service_name: str) -> HomeAssistantError:
    """Wrap a non-HA exception in a sanitized HomeAssistantError.

    HA exceptions (``HomeAssistantError``, ``Unauthorized``,
    ``ServiceValidationError``) propagate untouched so the framework
    preserves their status / translation context.
    """
    return HomeAssistantError(
        f"Service {service_name} failed: {sanitize_log_message(str(err))}"
    )


async def handle_print_text(call: ServiceCall) -> None:
    """Handle print_text service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(
                call.hass, entry.entry_id
            )
            _LOGGER.debug(
                "Service call: print_text for entry %s", entry.entry_id
            )
            await adapter.print_text(
                call.hass,
                text=call.data[ATTR_TEXT],
                align=call.data.get(ATTR_ALIGN) or defaults.get("align"),
                bold=call.data.get(ATTR_BOLD),
                underline=call.data.get(ATTR_UNDERLINE),
                width=call.data.get(ATTR_WIDTH),
                height=call.data.get(ATTR_HEIGHT),
                encoding=call.data.get(ATTR_ENCODING),
                cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
                feed=call.data.get(ATTR_FEED),
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Service print_text failed for entry %s", entry.entry_id
            )
            raise _wrap_unexpected(err, "print_text") from err


async def handle_print_text_utf8(call: ServiceCall) -> None:
    """Handle print_text_utf8 service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(
                call.hass, entry.entry_id
            )
            _LOGGER.debug(
                "Service call: print_text_utf8 for entry %s", entry.entry_id
            )
            text = call.data[ATTR_TEXT]
            codepage = config.codepage or "CP437"
            transcoded_text = await call.hass.async_add_executor_job(
                transcode_to_codepage, text, codepage
            )

            _LOGGER.debug(
                "Transcoded text from UTF-8 to %s: %d -> %d chars",
                codepage,
                len(text),
                len(transcoded_text),
            )

            await adapter.print_text(
                call.hass,
                text=transcoded_text,
                align=call.data.get(ATTR_ALIGN) or defaults.get("align"),
                bold=call.data.get(ATTR_BOLD),
                underline=call.data.get(ATTR_UNDERLINE),
                width=call.data.get(ATTR_WIDTH),
                height=call.data.get(ATTR_HEIGHT),
                encoding=None,  # printer uses configured codepage
                cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
                feed=call.data.get(ATTR_FEED),
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Service print_text_utf8 failed for entry %s", entry.entry_id
            )
            raise _wrap_unexpected(err, "print_text_utf8") from err


async def handle_print_qr(call: ServiceCall) -> None:
    """Handle print_qr service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(
                call.hass, entry.entry_id
            )
            _LOGGER.debug(
                "Service call: print_qr for entry %s", entry.entry_id
            )
            await adapter.print_qr(
                call.hass,
                data=call.data[ATTR_DATA],
                size=call.data.get(ATTR_SIZE),
                ec=call.data.get(ATTR_EC),
                align=call.data.get(ATTR_ALIGN) or defaults.get("align"),
                cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
                feed=call.data.get(ATTR_FEED),
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Service print_qr failed for entry %s", entry.entry_id
            )
            raise _wrap_unexpected(err, "print_qr") from err


async def _dispatch_print_image(
    call: ServiceCall, *, image_value: str, service_name: str
) -> None:
    """Shared logic for print_image and convenience services.

    The convenience services (print_camera_snapshot etc.) pass a single
    fully-resolved source string; the generic print_image runs the
    template renderer first. Both then funnel into the same kwarg
    extraction + adapter dispatch.
    """
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(
                call.hass, entry.entry_id
            )
            _LOGGER.debug(
                "Service call: %s for entry %s", service_name, entry.entry_id
            )
            image_kwargs = extract_image_kwargs(
                {**call.data, ATTR_IMAGE: image_value},
                defaults,
                prefix="",
            )
            await adapter.print_image(
                call.hass,
                cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
                feed=call.data.get(ATTR_FEED),
                context=call.context,
                **image_kwargs,
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Service %s failed for entry %s", service_name, entry.entry_id
            )
            raise _wrap_unexpected(err, service_name) from err


async def handle_print_image(call: ServiceCall) -> None:
    """Handle print_image service call."""
    image_value = render_template(call.hass, call.data[ATTR_IMAGE])
    await _dispatch_print_image(
        call, image_value=image_value, service_name="print_image"
    )


async def handle_print_camera_snapshot(call: ServiceCall) -> None:
    """Print a live snapshot from a camera entity."""
    await _dispatch_print_image(
        call,
        image_value=call.data["camera_entity"],
        service_name="print_camera_snapshot",
    )


async def handle_print_image_entity(call: ServiceCall) -> None:
    """Print the current frame from an HA image entity."""
    await _dispatch_print_image(
        call,
        image_value=call.data["image_entity"],
        service_name="print_image_entity",
    )


async def handle_print_image_url(call: ServiceCall) -> None:
    """Print an image fetched from an HTTP(S) URL."""
    await _dispatch_print_image(
        call, image_value=call.data["url"], service_name="print_image_url"
    )


async def handle_preview_image(call: ServiceCall) -> ServiceResponse:
    """Run the image pipeline and write the 1-bit PNG to disk.

    Returns ``{"path": ..., "width": ..., "height": ...}`` as a service
    response so automations / scripts can chain a media player or send
    the preview through a notification without re-running the pipeline.
    """
    target_entries = await _async_get_target_entries(call)
    if not target_entries:
        raise HomeAssistantError(
            "preview_image requires at least one printer target"
        )
    entry = target_entries[0]
    adapter, defaults, _ = _get_adapter_and_defaults(
        call.hass, entry.entry_id
    )
    image_value = render_template(call.hass, call.data[ATTR_IMAGE])

    from ..image_sources import resolve_image_bytes  # noqa: PLC0415
    from ..printer.image_operations import (  # noqa: PLC0415
        prepare_image_for_print,
    )

    # Reuse the production pipeline so the preview reflects what would
    # actually print. We accept the slight overhead of resolving image
    # bytes twice (once in prepare_image_for_print, once here for
    # source_kind) in exchange for code reuse.
    image_kwargs = extract_image_kwargs(
        {**call.data, ATTR_IMAGE: image_value}, defaults, prefix=""
    )
    image_kwargs.pop(ATTR_IMAGE, None)
    prepared = await prepare_image_for_print(
        adapter,
        call.hass,
        image_value,
        context=call.context,
        **image_kwargs,
    )

    output_path = call.data.get("output_path")
    if not output_path:
        output_path = f"/tmp/escpos_preview_{entry.entry_id}.png"  # noqa: S108
    # Allow /tmp as a sensible fallback even though it's outside the
    # allowlist — the user is in control of the value and previews
    # need somewhere to live by default.
    if (
        not call.hass.config.is_allowed_path(str(output_path))
        and not str(output_path).startswith("/tmp/")  # noqa: S108
    ):
        raise HomeAssistantError(
            f"output_path '{output_path}' is outside "
            "allowlist_external_dirs"
        )

    def _save() -> None:
        prepared.img_obj.save(output_path, format="PNG")

    await call.hass.async_add_executor_job(_save)
    _ = resolve_image_bytes  # imported above for visibility / future use

    return {
        "path": str(output_path),
        "width": prepared.img_obj.width,
        "height": prepared.img_obj.height,
        "slice_count": prepared.slice_count,
    }


def _build_calibration_png(width: int) -> bytes:
    """Build the calibration sheet PNG bytes (ruler + threshold sweep).

    Pulled to module scope so the executor closure doesn't capture the
    loop's ``adapter`` variable (ruff B023) and so it's independently
    unit-testable.
    """
    import base64  # noqa: PLC0415, F401
    from io import BytesIO  # noqa: PLC0415

    from PIL import Image, ImageDraw, ImageFont  # noqa: PLC0415

    thresholds = [80, 100, 120, 140, 160, 180, 200]
    strip_h = 80
    ruler_h = 40
    total_h = ruler_h + strip_h * len(thresholds)
    img = Image.new("L", (width, total_h), 255)
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default()
    # Ruler with major ticks every 64 px and labels.
    for x in range(0, width, 16):
        h = 20 if x % 64 == 0 else 8
        draw.line([(x, 0), (x, h)], fill=0, width=1)
        if x % 64 == 0:
            draw.text((x + 2, 20), str(x), fill=0, font=font)
    # Horizontal 0..255 gradient — same body for every strip, so the
    # user can read off the threshold by finding where it transitions
    # from black to white.
    gradient = Image.linear_gradient("L").resize((width, strip_h - 16))
    for i, t in enumerate(thresholds):
        y = ruler_h + i * strip_h
        draw.text((4, y + 2), f"threshold={t}", fill=0, font=font)
        img.paste(gradient, (0, y + 16))
    bio = BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


async def handle_calibration_print(call: ServiceCall) -> None:
    """Print a calibration sheet: ruler + threshold sweep strip.

    Helps users pick the right dither/threshold without burning a roll
    of paper trying different values. Each strip is labeled with its
    threshold value so the user can read off the best one.
    """
    import base64  # noqa: PLC0415

    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, _defaults, _ = _get_adapter_and_defaults(
                call.hass, entry.entry_id
            )
            _LOGGER.debug(
                "Service call: calibration_print for entry %s",
                entry.entry_id,
            )

            width = adapter._get_profile_pixel_width(call.hass) or 384
            raw = await call.hass.async_add_executor_job(
                _build_calibration_png, width
            )
            data_uri = (
                "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
            )
            await adapter.print_image(
                call.hass,
                image=data_uri,
                cut=call.data.get(ATTR_CUT, "full"),
                feed=call.data.get(ATTR_FEED, 2),
                context=call.context,
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Service calibration_print failed for entry %s",
                entry.entry_id,
            )
            raise _wrap_unexpected(err, "calibration_print") from err


async def handle_print_barcode(call: ServiceCall) -> None:
    """Handle print_barcode service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(
                call.hass, entry.entry_id
            )
            _LOGGER.debug(
                "Service call: print_barcode for entry %s", entry.entry_id
            )
            fs = call.data.get(ATTR_FORCE_SOFTWARE)
            # ``force_software`` accepts bool, "true"/"false", or the
            # python-escpos impl strings — schema validates the shape;
            # normalize the string-bool form here.
            if isinstance(fs, str) and fs.lower() in ("true", "false"):
                fs = fs.lower() == "true"
            await adapter.print_barcode(
                call.hass,
                code=call.data[ATTR_CODE],
                bc=call.data[ATTR_BC],
                height=call.data.get(ATTR_BARCODE_HEIGHT, 64),
                width=call.data.get(ATTR_BARCODE_WIDTH, 3),
                pos=call.data.get(ATTR_POS, "BELOW"),
                font=call.data.get(ATTR_FONT, "A"),
                align_ct=call.data.get(ATTR_ALIGN_CT, True),
                check=call.data.get(ATTR_CHECK, False),
                force_software=fs,
                align=defaults.get("align"),
                cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
                feed=call.data.get(ATTR_FEED),
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception(
                "Service print_barcode failed for entry %s", entry.entry_id
            )
            raise _wrap_unexpected(err, "print_barcode") from err
