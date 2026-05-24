"""Print operation service handlers."""

from __future__ import annotations

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
    sanitize_log_message,
    validate_font_path,
    validate_rows,
    validate_text_input,
)
from ..text_effects import render_box, render_table, render_text_image, resolve_style
from ..text_utils import transcode_to_codepage
from .target_resolution import _async_get_target_entries, _get_adapter_and_defaults

_LOGGER = logging.getLogger(__name__)


def _wrap_unexpected(err: Exception, service_name: str) -> HomeAssistantError:
    """Wrap a non-HA exception in a sanitized HomeAssistantError.

    HA exceptions (``HomeAssistantError``, ``Unauthorized``,
    ``ServiceValidationError``) propagate untouched so the framework
    preserves their status / translation context.
    """
    return HomeAssistantError(f"Service {service_name} failed: {sanitize_log_message(str(err))}")


def _is_font_path_allowed(hass: Any, resolved: Path) -> bool:
    """Decide whether the integration will load a font from ``resolved``.

    Accepts paths under HA's ``allowlist_external_dirs`` (the standard
    contract) *or* paths under ``<config>/fonts/`` (which we treat as
    locally trusted — the directory is created on integration setup
    and is intended exclusively for bundled-style font files). This
    removes the most common friction point: a user dropping a TTF in
    ``/config/fonts/`` without editing ``configuration.yaml``.

    The narrowing — only one well-known subdirectory of the HA config
    dir, only for font loading — keeps HA's broader allowlist model
    intact for other path-based services.
    """
    resolved_str = str(resolved)
    if hass.config.is_allowed_path(resolved_str):
        return True
    try:
        fonts_dir = Path(hass.config.path("fonts")).resolve()
    except OSError, ValueError:
        return False
    try:
        return Path(resolved_str).resolve().is_relative_to(fonts_dir)
    except OSError, ValueError:
        return False


async def handle_print_text(call: ServiceCall) -> None:
    """Handle print_text service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_text for entry %s", entry.entry_id)
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
            _LOGGER.exception("Service print_text failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_text") from err


async def handle_print_text_utf8(call: ServiceCall) -> None:
    """Handle print_text_utf8 service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_text_utf8 for entry %s", entry.entry_id)
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
            _LOGGER.exception("Service print_text_utf8 failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_text_utf8") from err


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
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_box for entry %s", entry.entry_id)
            laid_out, _ = await call.hass.async_add_executor_job(_render_box_layout, call, config)
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
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Service print_box failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_box") from err


async def handle_print_table(call: ServiceCall) -> None:
    """Handle print_table: render multi-column rows with optional borders."""
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_table for entry %s", entry.entry_id)
            laid_out, _ = await call.hass.async_add_executor_job(_render_table_layout, call, config)
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
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Service print_table failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_table") from err


async def handle_print_separator(call: ServiceCall) -> None:
    """Print a single decorative rule of repeated characters.

    ``char`` (validated to printable ASCII at the schema layer) is
    repeated to ``width`` (defaults to the printer's line width) and
    sent ``repeat`` times. Mirrors ``handle_print_box``'s shape but
    skips the renderer and codepage transcoder — single-byte ASCII
    needs no translation in any codepage we support.
    """
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_separator for entry %s", entry.entry_id)
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
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Service print_separator failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_separator") from err


async def handle_print_kvtable(call: ServiceCall) -> None:
    """Print a two-column label/value table (receipt totals etc.).

    Built on ``render_table`` with a label column (left-aligned) and a
    value column (per ``value_align``, default right). If
    ``label_width`` is omitted it is sized to the longest label,
    capped at ~60% of usable width so the value column still has room.
    """
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, config = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_kvtable for entry %s", entry.entry_id)
            items = call.data[ATTR_ITEMS]
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
        except HomeAssistantError:
            raise
        except Exception as err:
            _LOGGER.exception("Service print_kvtable failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_kvtable") from err


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
    output_path = await _resolve_preview_text_path(
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
    output_path = await _resolve_preview_text_path(
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
    import hashlib  # noqa: PLC0415

    return hashlib.sha256(entry_id.encode("utf-8")).hexdigest()[:16]


async def _resolve_preview_text_path(
    call: ServiceCall, *, requested: str | None, prefix: str, entry_id: str
) -> str:
    """Pick the output path for a text preview file.

    Defaults to ``<system tempdir>/{prefix}_{token}.txt`` where
    ``token`` is a non-reversible hash of the entry id (see
    :func:`_preview_filename_token`). Anything user-supplied is
    normalised via ``Path.resolve()`` then must satisfy HA's
    ``allowlist_external_dirs`` *or* live under the system tempdir —
    same contract as ``handle_preview_image``.
    """
    tempdir = Path(tempfile.gettempdir()).resolve()
    if not requested:
        return str(tempdir / f"{prefix}_{_preview_filename_token(entry_id)}.txt")
    try:
        resolved = Path(requested).resolve()
    except (OSError, ValueError) as exc:
        raise HomeAssistantError(f"Invalid output_path '{requested}': {exc}") from exc
    in_tempdir = False
    try:
        in_tempdir = resolved.is_relative_to(tempdir)
    except OSError, ValueError:
        in_tempdir = False
    resolved_str = str(resolved)
    if not call.hass.config.is_allowed_path(resolved_str) and not in_tempdir:
        raise HomeAssistantError(f"output_path '{resolved_str}' is outside allowlist_external_dirs")
    return resolved_str


def _write_text_file(path: str, content: str) -> None:
    """Write UTF-8 text to ``path``. Blocking — call on the executor."""
    Path(path).write_text(content, encoding="utf-8")


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
    from io import BytesIO  # noqa: PLC0415

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


async def handle_print_text_image(call: ServiceCall) -> None:
    """Render text to a PIL image (custom font + rotation) then print it.

    Rotation is applied to the rendered canvas BEFORE binarisation so
    the printed orientation matches what the user typed. The image-side
    ``rotation`` parameter is overridden to 0 when dispatching, so the
    image pipeline does not rotate a second time.
    """
    import base64  # noqa: PLC0415
    from functools import partial  # noqa: PLC0415

    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug(
                "Service call: print_text_image for entry %s",
                entry.entry_id,
            )
            font_name = call.data.get(ATTR_FONT_NAME) or "dejavu_mono"
            raw_font_path = call.data.get(ATTR_FONT_PATH)
            font_path: str | None = None
            if raw_font_path:
                # Filesystem validation (resolve + stat) is blocking; the
                # allowlist check is cheap so we run it on the main loop
                # after the resolver returns.
                resolved = await call.hass.async_add_executor_job(validate_font_path, raw_font_path)
                if not _is_font_path_allowed(call.hass, resolved):
                    raise HomeAssistantError(
                        f"Font path '{resolved}' is outside allowlist_external_dirs "
                        f"(and not under <config>/fonts/)"
                    )
                font_path = str(resolved)
                # When a user-supplied font is set, font_name is ignored.
                font_name = None

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
                "Service print_text_image failed for entry %s",
                entry.entry_id,
            )
            raise _wrap_unexpected(err, SERVICE_PRINT_TEXT_IMAGE) from err


async def handle_print_qr(call: ServiceCall) -> None:
    """Handle print_qr service call."""
    target_entries = await _async_get_target_entries(call)

    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_qr for entry %s", entry.entry_id)
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
            _LOGGER.exception("Service print_qr failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_qr") from err


async def _dispatch_print_image(call: ServiceCall, *, image_value: str, service_name: str) -> None:
    """Shared logic for print_image and convenience services.

    The convenience services (print_camera_snapshot etc.) pass a single
    fully-resolved source string; the generic print_image runs the
    template renderer first. Both then funnel into the same kwarg
    extraction + adapter dispatch.
    """
    target_entries = await _async_get_target_entries(call)
    for entry in target_entries:
        try:
            adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: %s for entry %s", service_name, entry.entry_id)
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
            _LOGGER.exception("Service %s failed for entry %s", service_name, entry.entry_id)
            raise _wrap_unexpected(err, service_name) from err


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
    image_kwargs = extract_image_kwargs({**call.data, ATTR_IMAGE: image_value}, defaults, prefix="")
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
    # Allow the system temp dir as a sensible fallback even though it's
    # outside the allowlist — the user is in control of the value and
    # previews need somewhere to live by default.
    try:
        in_tempdir = Path(output_path).is_relative_to(tempdir)
    except OSError, ValueError:
        in_tempdir = False
    if not call.hass.config.is_allowed_path(output_path) and not in_tempdir:
        raise HomeAssistantError(f"output_path '{output_path}' is outside allowlist_external_dirs")

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
            adapter, _defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug(
                "Service call: calibration_print for entry %s",
                entry.entry_id,
            )

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
            adapter, defaults, _ = _get_adapter_and_defaults(call.hass, entry.entry_id)
            _LOGGER.debug("Service call: print_barcode for entry %s", entry.entry_id)
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
            _LOGGER.exception("Service print_barcode failed for entry %s", entry.entry_id)
            raise _wrap_unexpected(err, "print_barcode") from err
