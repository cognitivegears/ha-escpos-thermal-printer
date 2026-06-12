"""Print operation service handlers."""

from __future__ import annotations

import base64
import hashlib
from io import BytesIO
import logging
from pathlib import Path
import tempfile
from typing import Any

from homeassistant.core import ServiceCall, ServiceResponse
from homeassistant.exceptions import HomeAssistantError

from ..const import (
    ATTR_ALIGN,
    ATTR_ALIGN_CT,
    ATTR_BARCODE_HEIGHT,
    ATTR_BARCODE_WIDTH,
    ATTR_BC,
    ATTR_BOLD,
    ATTR_CHAR,
    ATTR_CHECK,
    ATTR_CODE,
    ATTR_COLUMN_ALIGNS,
    ATTR_COLUMN_WIDTHS,
    ATTR_CUT,
    ATTR_DATA,
    ATTR_EC,
    ATTR_ENCODING,
    ATTR_FEED,
    ATTR_FONT,
    ATTR_FONT_NAME,
    ATTR_FONT_PATH,
    ATTR_FONT_SIZE,
    ATTR_FORCE_SOFTWARE,
    ATTR_HEADER,
    ATTR_HEIGHT,
    ATTR_IMAGE,
    ATTR_ITEMS,
    ATTR_LABEL_WIDTH,
    ATTR_LINE_SPACING,
    ATTR_OUTPUT_PATH,
    ATTR_PADDING,
    ATTR_POS,
    ATTR_REPEAT,
    ATTR_ROTATION,
    ATTR_ROW_SEPARATORS,
    ATTR_ROWS,
    ATTR_SIZE,
    ATTR_STYLE,
    ATTR_TEXT,
    ATTR_TOTAL_WIDTH,
    ATTR_UNDERLINE,
    ATTR_VALUE_ALIGN,
    ATTR_WIDTH,
    DEFAULT_BORDER_STYLE,
    DEFAULT_LINE_WIDTH,
    SERVICE_PREVIEW_BOX,
    SERVICE_PREVIEW_TABLE,
    SERVICE_PRINT_BOX,
    SERVICE_PRINT_CAMERA_SNAPSHOT,
    SERVICE_PRINT_IMAGE,
    SERVICE_PRINT_IMAGE_ENTITY,
    SERVICE_PRINT_IMAGE_PATH,
    SERVICE_PRINT_IMAGE_URL,
    SERVICE_PRINT_KVTABLE,
    SERVICE_PRINT_TABLE,
    SERVICE_PRINT_TEXT_IMAGE,
)
from ..image_sources import extract_image_kwargs, render_template
from ..security import (
    sanitise_kv_items,
    validate_font_path_with_fonts_dir,
    validate_rows,
    validate_text_input,
    write_file_no_follow,
)
from ..text_effects import render_box, render_table, render_text_image, resolve_style
from ..text_utils import transcode_to_codepage
from ._handler_utils import _for_each_target
from .target_resolution import _async_get_target_entries, _get_adapter_and_defaults

_LOGGER = logging.getLogger(__name__)


async def handle_print_text(call: ServiceCall) -> None:
    """Handle print_text service call."""

    async def _body(entry: Any, adapter: Any, defaults: Any, _config: Any) -> None:
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

    await _for_each_target(call, "print_text", _body)


async def handle_print_text_utf8(call: ServiceCall) -> None:
    """Handle print_text_utf8 service call."""

    async def _body(entry: Any, adapter: Any, defaults: Any, config: Any) -> None:
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

    await _for_each_target(call, "print_text_utf8", _body)


async def _render_text_layout_for_codepage(
    call: ServiceCall, layout_text: str, *, service_name: str, entry_id: str
) -> tuple[str, str]:
    """Transcode an already-laid-out Unicode string to the printer codepage.

    Returns ``(transcoded_text, codepage)``. The layout (box / table)
    must already account for one printer column per char. The
    transcoder substitutes ASCII lookalikes for any glyph not native to
    ``codepage``, preserving column count (every entry in the lookalike
    map for box-drawing glyphs is a single-char replacement).
    """
    _adapter, _defaults, config = _get_adapter_and_defaults(call.hass, entry_id)
    codepage = config.codepage or "CP437"
    transcoded = await call.hass.async_add_executor_job(
        transcode_to_codepage, layout_text, codepage
    )
    _LOGGER.debug(
        "%s transcoded %d chars to %s for entry %s",
        service_name,
        len(layout_text),
        codepage,
        entry_id,
    )
    return transcoded, codepage


def _line_width_for(config: object) -> int:
    """Pull the printer's configured line width with a safe default."""
    return int(getattr(config, "line_width", DEFAULT_LINE_WIDTH) or DEFAULT_LINE_WIDTH)


def _render_box_layout(call: ServiceCall, config: object) -> tuple[str, str]:
    """Sanitise + run ``render_box``. Returns ``(laid_out_text, codepage)``.

    Shared by both ``handle_print_box`` (which then transcodes and prints)
    and ``handle_preview_box`` (which writes the layout to disk). Keeping
    the layout in one place stops the two handlers drifting on field
    handling.
    """
    style = call.data.get(ATTR_STYLE, DEFAULT_BORDER_STYLE)
    padding = int(call.data.get(ATTR_PADDING, 0))
    align = call.data.get(ATTR_ALIGN, "left")
    codepage = getattr(config, "codepage", None) or "CP437"
    outer_width = int(call.data.get(ATTR_TOTAL_WIDTH) or _line_width_for(config))
    # The renderer draws ``v`` + content + ``v`` on each row when the
    # resolved style emits side borders; with ``style="none"`` no border
    # glyphs are drawn, so the user-facing total width *is* the inner
    # width. Reserving 2 cells unconditionally would silently shrink
    # borderless output by two columns.
    resolved_style = resolve_style(style, codepage)
    border_overhead = 0 if resolved_style == "none" else 2
    inner_width = max(1, outer_width - border_overhead)
    sanitised_text = validate_text_input(call.data[ATTR_TEXT])
    laid_out = render_box(
        sanitised_text,
        inner_width=inner_width,
        style=style,
        codepage=codepage,
        padding=padding,
        align=align,
    )
    return laid_out, codepage


def _render_table_layout(call: ServiceCall, config: object) -> tuple[str, str]:
    """Sanitise + run ``render_table``. Returns ``(laid_out_text, codepage)``.

    Counterpart to :func:`_render_box_layout` — shared by
    ``handle_print_table`` and ``handle_preview_table``.
    """
    sanitised_rows = validate_rows(call.data[ATTR_ROWS])
    style = call.data.get(ATTR_STYLE, DEFAULT_BORDER_STYLE)
    header = bool(call.data.get(ATTR_HEADER, False))
    row_separators = bool(call.data.get(ATTR_ROW_SEPARATORS, False))
    total_width = int(call.data.get(ATTR_TOTAL_WIDTH) or _line_width_for(config))
    codepage = getattr(config, "codepage", None) or "CP437"
    laid_out = render_table(
        sanitised_rows,
        total_width=total_width,
        column_widths=call.data.get(ATTR_COLUMN_WIDTHS),
        column_aligns=call.data.get(ATTR_COLUMN_ALIGNS),
        style=style,
        codepage=codepage,
        header=header,
        row_separators=row_separators,
    )
    return laid_out, codepage


async def handle_print_box(call: ServiceCall) -> None:
    """Handle print_box: wrap user text in a printable border."""

    async def _body(entry: Any, adapter: Any, defaults: Any, config: Any) -> None:
        # ``render_box`` cost is small (P-M1: ~2 ms at MAX_TEXT_LENGTH); the
        # executor-dispatch overhead is comparable, so run inline.
        laid_out, _ = _render_box_layout(call, config)
        transcoded, _ = await _render_text_layout_for_codepage(
            call,
            laid_out,
            service_name=SERVICE_PRINT_BOX,
            entry_id=entry.entry_id,
        )
        await adapter.print_text(
            call.hass,
            text=transcoded,
            align=defaults.get("align"),
            bold=None,
            underline=None,
            width=None,
            height=None,
            encoding=None,
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
        )

    await _for_each_target(call, "print_box", _body)


async def handle_print_table(call: ServiceCall) -> None:
    """Handle print_table: render multi-column rows with optional borders."""

    async def _body(entry: Any, adapter: Any, defaults: Any, config: Any) -> None:
        # Table rendering can be expensive (200x12 = ~400 ms at max);
        # keep it on the executor (P-M1 separates this from print_box).
        laid_out, _ = await call.hass.async_add_executor_job(
            _render_table_layout, call, config
        )
        transcoded, _ = await _render_text_layout_for_codepage(
            call,
            laid_out,
            service_name=SERVICE_PRINT_TABLE,
            entry_id=entry.entry_id,
        )
        await adapter.print_text(
            call.hass,
            text=transcoded,
            align=defaults.get("align"),
            bold=None,
            underline=None,
            width=None,
            height=None,
            encoding=None,
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
        )

    await _for_each_target(call, "print_table", _body)


async def handle_print_separator(call: ServiceCall) -> None:
    """Print a single decorative rule of repeated characters.

    ``char`` (validated to printable ASCII at the schema layer) is
    repeated to ``width`` (defaults to the printer's line width) and
    sent ``repeat`` times. Mirrors ``handle_print_box``'s shape but
    skips the renderer and codepage transcoder — single-byte ASCII
    needs no translation in any codepage we support.
    """

    async def _body(entry: Any, adapter: Any, defaults: Any, config: Any) -> None:
        char = call.data.get(ATTR_CHAR, "-")
        width = int(call.data.get(ATTR_WIDTH) or _line_width_for(config))
        repeat = int(call.data.get(ATTR_REPEAT, 1))
        line = char * width
        text = "\n".join([line] * repeat)
        await adapter.print_text(
            call.hass,
            text=text,
            align=defaults.get("align"),
            bold=None,
            underline=None,
            width=None,
            height=None,
            encoding=None,
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
        )

    await _for_each_target(call, "print_separator", _body)


async def handle_print_kvtable(call: ServiceCall) -> None:
    """Print a two-column label/value table (receipt totals etc.).

    Built on ``render_table`` with a label column (left-aligned) and a
    value column (per ``value_align``, default right). If
    ``label_width`` is omitted it is sized to the longest label,
    capped at ~60% of usable width so the value column still has room.
    """

    async def _body(entry: Any, adapter: Any, defaults: Any, config: Any) -> None:
        # P-H1: sanitise items on the executor (per-cell regex passes scale
        # with payload size and shouldn't run on the event loop).
        items = await call.hass.async_add_executor_job(
            sanitise_kv_items, call.data[ATTR_ITEMS]
        )
        style = call.data.get(ATTR_STYLE, "none")
        value_align = call.data.get(ATTR_VALUE_ALIGN, "right")
        total_width = int(call.data.get(ATTR_TOTAL_WIDTH) or _line_width_for(config))
        codepage = getattr(config, "codepage", None) or "CP437"
        label_width = call.data.get(ATTR_LABEL_WIDTH)
        column_widths = _kvtable_widths(
            items=items,
            total_width=total_width,
            style=style,
            label_width=label_width,
        )
        laid_out = await call.hass.async_add_executor_job(
            _render_kvtable_layout,
            items,
            total_width,
            column_widths,
            value_align,
            style,
            codepage,
        )
        transcoded, _ = await _render_text_layout_for_codepage(
            call,
            laid_out,
            service_name=SERVICE_PRINT_KVTABLE,
            entry_id=entry.entry_id,
        )
        await adapter.print_text(
            call.hass,
            text=transcoded,
            align=defaults.get("align"),
            bold=None,
            underline=None,
            width=None,
            height=None,
            encoding=None,
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
        )

    await _for_each_target(call, "print_kvtable", _body)


def _render_kvtable_layout(
    items: list[list[str]],
    total_width: int,
    column_widths: list[int],
    value_align: str,
    style: str,
    codepage: str,
) -> str:
    """Render the kvtable. Blocking — call via the executor.

    Items are already validated *and* sanitised by
    :func:`services.schemas._validate_kv_items` at the schema layer, so
    we don't re-run ``validate_rows`` here (which would double-check
    the structure and produce a second error message for the same
    failure mode).
    """
    return render_table(
        items,
        total_width=total_width,
        column_widths=column_widths,
        column_aligns=["left", value_align],
        style=style,
        codepage=codepage,
        header=False,
        row_separators=False,
    )


def _kvtable_widths(
    *,
    items: list[list[str]],
    total_width: int,
    style: str,
    label_width: int | None,
) -> list[int]:
    """Pick label/value column widths for ``print_kvtable``.

    Borders consume 3 columns (``|L|V|``) when bordered, or 1 inter-
    column gap when borderless. With an explicit ``label_width`` the
    value column gets the remainder. With auto-sizing, the label
    column matches the longest label, capped at ~60% of total width
    (and at least 1) so the value column still has room.
    """
    bordered = style != "none"
    overhead = 3 if bordered else 1
    usable = max(2, total_width - overhead)
    if label_width is not None:
        lw = min(int(label_width), usable - 1)
        lw = max(1, lw)
        return [lw, usable - lw]
    longest = max((len(str(row[0])) for row in items), default=1)
    cap = max(1, (usable * 6) // 10)  # ~60% of usable
    lw = max(1, min(longest, cap, usable - 1))
    return [lw, usable - lw]


async def handle_preview_box(call: ServiceCall) -> ServiceResponse:
    """Render a ``print_box`` layout to a ``.txt`` file (no printing).

    Returns ``{"path": ..., "width": ..., "line_count": ..., "codepage": ...}``
    so automations can chain a notification or open the file. The
    rendered text is transcoded to the printer's codepage with ASCII
    fallbacks so the file reflects what would actually print.
    """
    target_entries = await _async_get_target_entries(call)
    if not target_entries:
        raise HomeAssistantError("preview_box requires at least one printer target")
    if len(target_entries) > 1:
        # The response shape is a single {path, width, line_count, codepage}
        # tuple, so silently picking the first target would write one file
        # with metadata that doesn't necessarily match what the caller
        # intended. Make the contract explicit.
        raise HomeAssistantError(
            "preview_box requires exactly one printer target; "
            f"got {len(target_entries)}. Call preview_box once per device."
        )
    entry = target_entries[0]
    _adapter, _defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
    laid_out, codepage = await call.hass.async_add_executor_job(_render_box_layout, call, config)
    transcoded, _ = await _render_text_layout_for_codepage(
        call,
        laid_out,
        service_name=SERVICE_PREVIEW_BOX,
        entry_id=entry.entry_id,
    )
    output_path = _resolve_preview_text_path(
        call,
        requested=call.data.get(ATTR_OUTPUT_PATH),
        prefix="escpos_preview_box",
        entry_id=entry.entry_id,
    )
    await call.hass.async_add_executor_job(_write_text_file, output_path, transcoded)
    lines = transcoded.splitlines() or [""]
    return {
        "path": str(output_path),
        "width": max((len(line) for line in lines), default=0),
        "line_count": len(lines),
        "codepage": codepage,
    }


async def handle_preview_table(call: ServiceCall) -> ServiceResponse:
    """Render a ``print_table`` layout to a ``.txt`` file (no printing)."""
    target_entries = await _async_get_target_entries(call)
    if not target_entries:
        raise HomeAssistantError("preview_table requires at least one printer target")
    if len(target_entries) > 1:
        raise HomeAssistantError(
            "preview_table requires exactly one printer target; "
            f"got {len(target_entries)}. Call preview_table once per device."
        )
    entry = target_entries[0]
    _adapter, _defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
    laid_out, codepage = await call.hass.async_add_executor_job(_render_table_layout, call, config)
    transcoded, _ = await _render_text_layout_for_codepage(
        call,
        laid_out,
        service_name=SERVICE_PREVIEW_TABLE,
        entry_id=entry.entry_id,
    )
    output_path = _resolve_preview_text_path(
        call,
        requested=call.data.get(ATTR_OUTPUT_PATH),
        prefix="escpos_preview_table",
        entry_id=entry.entry_id,
    )
    await call.hass.async_add_executor_job(_write_text_file, output_path, transcoded)
    lines = transcoded.splitlines() or [""]
    return {
        "path": str(output_path),
        "width": max((len(line) for line in lines), default=0),
        "line_count": len(lines),
        "codepage": codepage,
    }


def _preview_filename_token(entry_id: str) -> str:
    """Return a short non-reversible token for default preview filenames.

    Using the raw ``entry_id`` in a world-readable ``/tmp`` filename
    lets any local user on the host enumerate which integration entries
    exist (and how many times each was previewed). A truncated SHA256
    keeps filenames stable per entry — so re-running the same preview
    overwrites the previous file rather than spamming /tmp — without
    exposing the underlying id.
    """
    return hashlib.sha256(entry_id.encode("utf-8")).hexdigest()[:16]


def _resolve_preview_text_path(
    call: ServiceCall, *, requested: str | None, prefix: str, entry_id: str
) -> str:
    """Pick the output path for a text preview file.

    Defaults to ``<system tempdir>/{prefix}_{token}.txt`` where
    ``token`` is a non-reversible hash of the entry id (see
    :func:`_preview_filename_token`).

    User-supplied ``output_path`` is restricted to the system tempdir
    (S-M5: a non-admin HA user could otherwise overwrite any file in
    ``allowlist_external_dirs`` — e.g. ``/config/configuration.yaml``
    — with rendered text). Previews are designed for one-off chaining
    with notifications / media players; persistent output should be
    written by the automation itself, not by a preview service.
    """
    tempdir = Path(tempfile.gettempdir()).resolve()
    if not requested:
        return str(tempdir / f"{prefix}_{_preview_filename_token(entry_id)}.txt")
    try:
        resolved = Path(requested).resolve()
    except (OSError, ValueError) as exc:
        raise HomeAssistantError(f"Invalid output_path '{requested}': {exc}") from exc
    try:
        in_tempdir = resolved.is_relative_to(tempdir)
    except (OSError, ValueError):
        in_tempdir = False
    if not in_tempdir:
        raise HomeAssistantError(
            f"output_path '{resolved}' must be inside the system temp directory "
            f"({tempdir}); use a regular service / script to write elsewhere."
        )
    return str(resolved)


def _write_text_file(path: str, content: str) -> None:
    """Write UTF-8 text to ``path`` with O_NOFOLLOW (S-M2). Blocking."""
    write_file_no_follow(path, content.encode("utf-8"))


def _render_text_image_to_png_bytes(
    *,
    text: str,
    font_name: str | None,
    font_path: str | None,
    font_size: int,
    max_width_px: int,
    line_spacing: float,
    rotation: int,
    align: str,
) -> bytes:
    """Render text + save to PNG bytes. Blocking — call on the executor.

    Pulled to module scope so the executor closure does not capture the
    per-entry ``adapter`` variable (ruff B023) and so the function is
    independently unit-testable.
    """
    img = render_text_image(
        text,
        font_name=font_name,
        font_path=font_path,
        font_size=font_size,
        max_width_px=max_width_px,
        line_spacing=line_spacing,
        rotation=rotation,
        align=align,
    )
    bio = BytesIO()
    img.save(bio, format="PNG")
    return bio.getvalue()


async def _prepare_text_image_kwargs(
    call: ServiceCall, adapter: Any, defaults: dict[str, Any]
) -> tuple[dict[str, Any], str | None, int | None]:
    """Render the text canvas and assemble the print_image kwargs.

    Returns ``(image_kwargs, cut, feed)``. Encapsulates the
    font-resolution → render → base64-encode → image-kwargs pipeline so
    the dispatching handler stays focused on the per-target loop (M3).
    """
    from functools import partial  # noqa: PLC0415

    font_name = call.data.get(ATTR_FONT_NAME) or "dejavu_mono"
    raw_font_path = call.data.get(ATTR_FONT_PATH)
    font_path: str | None = None
    if raw_font_path:
        # Single executor hop: validate path (which honours <config>/fonts/
        # narrowed trust) and resolve. S-M1 moved the allowlist decision
        # into security.py so all trust-boundary checks live together.
        resolved = await call.hass.async_add_executor_job(
            validate_font_path_with_fonts_dir, raw_font_path, call.hass
        )
        font_path = str(resolved)
        font_name = None  # user-supplied path wins; ignore named choice

    font_size = int(call.data.get(ATTR_FONT_SIZE, 16))
    line_spacing = float(call.data.get(ATTR_LINE_SPACING, 1.1))
    rotation = int(call.data.get(ATTR_ROTATION, 0))
    align = call.data.get(ATTR_ALIGN) or defaults.get("align") or "left"
    profile_width = adapter.get_profile_pixel_width(call.hass)
    max_width_px = int(profile_width or 384)

    png_bytes = await call.hass.async_add_executor_job(
        partial(
            _render_text_image_to_png_bytes,
            text=call.data[ATTR_TEXT],
            font_name=font_name,
            font_path=font_path,
            font_size=font_size,
            max_width_px=max_width_px,
            line_spacing=line_spacing,
            rotation=rotation,
            align=align,
        )
    )
    data_uri = "data:image/png;base64," + base64.b64encode(png_bytes).decode("ascii")

    # The text canvas is already in its final orientation/alignment.
    # Force ``image_rotation`` to 0 so the image pipeline doesn't
    # rotate a second time, and pass the text-side ``align`` as
    # ``image_align`` so the canvas lands where the user expects.
    image_kwargs = extract_image_kwargs(
        {
            **call.data,
            ATTR_IMAGE: data_uri,
            "image_rotation": 0,
            "image_align": align,
        },
        defaults,
        prefix="image_",
        hass=call.hass,
    )
    cut = call.data.get(ATTR_CUT) or defaults.get("cut")
    feed = call.data.get(ATTR_FEED)
    return image_kwargs, cut, feed


async def handle_print_text_image(call: ServiceCall) -> None:
    """Render text to a PIL image (custom font + rotation) then print it.

    Rotation is applied to the rendered canvas BEFORE binarisation so
    the printed orientation matches what the user typed. The image-side
    ``rotation`` parameter is overridden to 0 when dispatching, so the
    image pipeline does not rotate a second time.
    """

    async def _body(entry: Any, adapter: Any, defaults: Any, _config: Any) -> None:
        image_kwargs, cut, feed = await _prepare_text_image_kwargs(call, adapter, defaults)
        await adapter.print_image(
            call.hass,
            cut=cut,
            feed=feed,
            context=call.context,
            **image_kwargs,
        )

    await _for_each_target(call, SERVICE_PRINT_TEXT_IMAGE, _body)


async def handle_print_qr(call: ServiceCall) -> None:
    """Handle print_qr service call."""

    async def _body(entry: Any, adapter: Any, defaults: Any, _config: Any) -> None:
        await adapter.print_qr(
            call.hass,
            data=call.data[ATTR_DATA],
            size=call.data.get(ATTR_SIZE),
            ec=call.data.get(ATTR_EC),
            align=call.data.get(ATTR_ALIGN) or defaults.get("align"),
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
        )

    await _for_each_target(call, "print_qr", _body)


async def _dispatch_print_image(call: ServiceCall, *, image_value: str, service_name: str) -> None:
    """Shared logic for print_image and convenience services.

    The convenience services (print_camera_snapshot etc.) pass a single
    fully-resolved source string; the generic print_image runs the
    template renderer first. Both then funnel into the same kwarg
    extraction + adapter dispatch.
    """

    async def _body(entry: Any, adapter: Any, defaults: Any, _config: Any) -> None:
        image_kwargs = extract_image_kwargs(
            {**call.data, ATTR_IMAGE: image_value},
            defaults,
            prefix="",
            hass=call.hass,
        )
        await adapter.print_image(
            call.hass,
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
            context=call.context,
            **image_kwargs,
        )

    await _for_each_target(call, service_name, _body)


async def handle_print_image(call: ServiceCall) -> None:
    """Handle print_image service call."""
    image_value = render_template(call.hass, call.data[ATTR_IMAGE])
    await _dispatch_print_image(call, image_value=image_value, service_name=SERVICE_PRINT_IMAGE)


async def handle_print_camera_snapshot(call: ServiceCall) -> None:
    """Print a live snapshot from a camera entity."""
    await _dispatch_print_image(
        call,
        image_value=call.data["camera_entity"],
        service_name=SERVICE_PRINT_CAMERA_SNAPSHOT,
    )


async def handle_print_image_entity(call: ServiceCall) -> None:
    """Print the current frame from an HA image entity."""
    await _dispatch_print_image(
        call,
        image_value=call.data["image_entity"],
        service_name=SERVICE_PRINT_IMAGE_ENTITY,
    )


async def handle_print_image_url(call: ServiceCall) -> None:
    """Print an image fetched from an HTTP(S) URL."""
    await _dispatch_print_image(
        call, image_value=call.data["url"], service_name=SERVICE_PRINT_IMAGE_URL
    )


async def handle_print_image_path(call: ServiceCall) -> None:
    """Print an image read from a local file path."""
    await _dispatch_print_image(
        call, image_value=call.data["path"], service_name=SERVICE_PRINT_IMAGE_PATH
    )


_PREVIEW_IGNORED_KEYS = frozenset(
    {"high_density", "impl", "fragment_height", "chunk_delay_ms", "center", "cut", "feed"}
)


async def handle_preview_image(call: ServiceCall) -> ServiceResponse:
    """Run the image pipeline and write the 1-bit PNG to disk.

    Returns ``{"path": ..., "width": ..., "height": ...}`` as a service
    response so automations / scripts can chain a media player or send
    the preview through a notification without re-running the pipeline.
    """
    target_entries = await _async_get_target_entries(call)
    if not target_entries:
        raise HomeAssistantError("preview_image requires at least one printer target")
    if len(target_entries) > 1:
        raise HomeAssistantError(
            "preview_image requires exactly one printer target; "
            f"got {len(target_entries)}. Call preview_image once per device."
        )
    entry = target_entries[0]
    adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
    # Surface — at debug level — any printer-communication keys the caller
    # passed. preview_image silently ignores them (they don't affect the
    # PNG written to disk); the log line helps users diagnose "I set
    # fragment_height but the preview looks the same" confusion.
    passed_printer_only = _PREVIEW_IGNORED_KEYS & call.data.keys()
    if passed_printer_only:
        _LOGGER.debug(
            "preview_image ignoring printer-only keys (no effect on PNG): %s",
            sorted(passed_printer_only),
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
        {**call.data, ATTR_IMAGE: image_value}, defaults, prefix="", hass=call.hass
    )
    image_kwargs.pop(ATTR_IMAGE, None)
    prepared = await prepare_image_for_print(
        adapter,
        call.hass,
        image_value,
        context=call.context,
        **image_kwargs,
    )

    raw_output_path = call.data.get("output_path")
    tempdir = Path(tempfile.gettempdir()).resolve()
    if not raw_output_path:
        # Hashed entry token (not the raw id) keeps the /tmp filename
        # from leaking which integration entries exist on the host.
        output_path = str(tempdir / f"escpos_preview_{_preview_filename_token(entry.entry_id)}.png")
    else:
        try:
            output_path = str(Path(str(raw_output_path)).resolve())
        except (OSError, ValueError) as exc:
            raise HomeAssistantError(f"Invalid output_path '{raw_output_path}': {exc}") from exc
    # S-M5: restrict user-supplied output_path to the system tempdir. A
    # non-admin HA user could otherwise call preview_image with
    # output_path=/config/configuration.yaml and clobber it with PNG
    # bytes. Previews are for one-off chaining with notifications;
    # persistent output belongs in a regular automation step.
    try:
        in_tempdir = Path(output_path).is_relative_to(tempdir)
    except (OSError, ValueError):
        in_tempdir = False
    if not in_tempdir:
        raise HomeAssistantError(
            f"output_path '{output_path}' must be inside the system temp directory "
            f"({tempdir}); use a regular service to write elsewhere."
        )

    def _save() -> None:
        # S-M2: render to bytes in-memory then write via O_NOFOLLOW so a
        # swapped symlink between path-validation and image-save can't
        # redirect us into an arbitrary file under tempdir.
        bio = BytesIO()
        prepared.img_obj.save(bio, format="PNG")
        write_file_no_follow(output_path, bio.getvalue())

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
    # PIL is lazy-imported — it's heavy and only loaded when the
    # calibration sheet is actually requested.
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

    async def _body(entry: Any, adapter: Any, _defaults: Any, _config: Any) -> None:
        width = adapter.get_profile_pixel_width(call.hass) or 384
        raw = await call.hass.async_add_executor_job(_build_calibration_png, width)
        data_uri = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        await adapter.print_image(
            call.hass,
            image=data_uri,
            cut=call.data.get(ATTR_CUT, "full"),
            feed=call.data.get(ATTR_FEED, 2),
            context=call.context,
        )

    await _for_each_target(call, "calibration_print", _body)


async def handle_print_barcode(call: ServiceCall) -> None:
    """Handle print_barcode service call."""

    async def _body(entry: Any, adapter: Any, defaults: Any, _config: Any) -> None:
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
            align=call.data.get(ATTR_ALIGN) or defaults.get("align"),
            cut=call.data.get(ATTR_CUT) or defaults.get("cut"),
            feed=call.data.get(ATTR_FEED),
        )

    await _for_each_target(call, "print_barcode", _body)
