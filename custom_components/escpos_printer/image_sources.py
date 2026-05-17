"""Resolve a print_image source string into raw image bytes.

Supported source forms (detected via :func:`_classify`):

1. ``data:image/<subtype>;base64,...`` data URI.
2. ``camera.<id>`` Home Assistant camera entity.
3. ``image.<id>`` Home Assistant image entity.
4. ``http://`` or ``https://`` URL.
5. Local file path (must be inside ``allowlist_external_dirs``).

The resolver returns the raw bytes plus an optional content-type hint
for diagnostics. Decoding/processing happens downstream in
``printer/image_processor``.

This module lives at the package root (not under ``printer/``) because
it is a Home-Assistant resource fetcher — it depends on HA components
and helpers, not on the vendored ``python-escpos`` adapter layer.
"""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import TYPE_CHECKING, Any, Literal
from urllib.parse import urljoin

import aiohttp
from homeassistant.auth.permissions.const import POLICY_READ
from homeassistant.core import Context
from homeassistant.exceptions import HomeAssistantError, Unauthorized
from homeassistant.helpers.template import Template

from .const import (
    ATTR_ALIGN,
    ATTR_AUTO_RESIZE,
    ATTR_AUTOCONTRAST,
    ATTR_CENTER,
    ATTR_CHUNK_DELAY_MS,
    ATTR_DITHER,
    ATTR_FALLBACK_IMAGE,
    ATTR_FRAGMENT_HEIGHT,
    ATTR_HIGH_DENSITY,
    ATTR_IMAGE,
    ATTR_IMAGE_WIDTH,
    ATTR_IMPL,
    ATTR_INVERT,
    ATTR_MIRROR,
    ATTR_ROTATION,
    ATTR_THRESHOLD,
)
from .security import (
    MAX_IMAGE_SIZE_MB,
    _validate_local_path_sync,
    open_local_image_no_follow,
    sanitize_log_message,
    validate_base64_image,
    validate_entity_id_for_domain,
    validate_image_url,
    validate_image_url_and_resolve,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

_HTTP_CONNECT_TIMEOUT = 5.0
_HTTP_READ_TIMEOUT = 5.0
_HTTP_TOTAL_TIMEOUT = 10.0
_ENTITY_FETCH_TIMEOUT_SECONDS = 10
_MAX_BYTES = MAX_IMAGE_SIZE_MB * 1024 * 1024
# When auto_resize=True the integration accepts up to 4x the normal
# raw-bytes cap and immediately downscales after decode (see
# ``image_processor.process_image``). This keeps 12 MB phone JPEGs and
# 20 MP camera snapshots working without raising the *processed* pixel
# cap, which is the real DoS axis.
_MAX_BYTES_AUTO_RESIZE = MAX_IMAGE_SIZE_MB * 1024 * 1024 * 4
_MAX_REDIRECTS = 5

# Public sentinel strings returned in the optional content-type hint slot
# so callers / tests can rely on stable identifiers regardless of the
# upstream Content-Type header.
SOURCE_DATA_URI = "data-uri"
SOURCE_LOCAL_FILE = "local-file"

SourceKind = Literal["data", "camera", "image", "http", "local"]


def classify_source(source: str) -> tuple[SourceKind, str]:
    """Return ``(kind, cleaned_source)`` for a print_image source string.

    Public helper so the adapter can update its image-pipeline diagnostics
    counters without re-implementing source-form detection.
    """
    return _classify(source)


def _classify(source: str) -> tuple[SourceKind, str]:
    """Return ``(kind, cleaned_source)`` for a print_image source string."""
    stripped = source.strip()
    lower = stripped.lower()
    if lower.startswith("data:"):
        if not lower.startswith("data:image/"):
            raise HomeAssistantError(
                "Only data:image/<subtype>;base64,... data URIs are supported"
            )
        return "data", stripped
    if lower.startswith("camera."):
        return "camera", stripped
    if lower.startswith("image."):
        return "image", stripped
    if lower.startswith(("http://", "https://")):
        return "http", stripped
    return "local", stripped


def render_template(hass: HomeAssistant, value: Any) -> str:
    """Render ``value`` as a Jinja template if it looks like one.

    Accepts either a ``Template`` object (as produced by ``cv.template``
    in a service schema) or a raw string. The string fast-path avoids
    constructing a ``Template`` for the common case where no template
    syntax is present.
    """
    if isinstance(value, Template):
        if value.hass is None:
            value.hass = hass
        rendered: Any = value.async_render(parse_result=False)
        return str(rendered)
    if not isinstance(value, str):
        raise HomeAssistantError("Image source must be a string or template")
    if "{{" in value or "{%" in value:
        tpl = Template(value, hass)
        rendered = tpl.async_render(parse_result=False)
        return str(rendered)
    return value


async def resolve_image_bytes(
    hass: HomeAssistant,
    source: str,
    *,
    context: Context | None = None,
    auto_resize: bool = False,
) -> tuple[bytes, str | None]:
    """Resolve ``source`` to ``(raw_bytes, content_type_hint)``.

    ``context`` is used by the camera/image entity resolvers to enforce
    the calling user's per-entity permissions (see HA core ``Unauthorized``).
    Pass ``ServiceCall.context`` or the notify entity service ``context``
    through.

    ``auto_resize`` raises the raw-bytes cap to 4x the normal limit so
    a 12 MB phone JPEG decoded from a camera/URL is acceptable. The
    image processor will then ``.thumbnail()`` the decoded image down
    before any expensive work happens.
    """
    if not isinstance(source, str) or not source.strip():
        raise HomeAssistantError("Image source must be a non-empty string")

    kind, value = _classify(source)
    match kind:
        case "data":
            _LOGGER.debug("Resolving base64 data URI image (len=%d)", len(value))
            return validate_base64_image(value), SOURCE_DATA_URI
        case "camera":
            return await _resolve_camera(
                hass, value, context=context, auto_resize=auto_resize
            )
        case "image":
            return await _resolve_image_entity(
                hass, value, context=context, auto_resize=auto_resize
            )
        case "http":
            return await _resolve_http(hass, value, auto_resize=auto_resize)
        case "local":
            return await _resolve_local(hass, value, auto_resize=auto_resize)


async def _check_user_can_read_entity(
    hass: HomeAssistant, context: Context | None, entity_id: str
) -> None:
    """Raise :class:`Unauthorized` if ``context``'s user can't read ``entity_id``.

    Internal/service calls without a ``user_id`` (e.g. integrations
    invoking each other) pass through unrestricted; admins bypass.
    """
    if context is None or context.user_id is None:
        return
    user = await hass.auth.async_get_user(context.user_id)
    if user is None or user.is_admin:
        return
    if not user.permissions.check_entity(entity_id, POLICY_READ):
        raise Unauthorized(
            context=context, entity_id=entity_id, permission=POLICY_READ
        )


async def _resolve_camera(
    hass: HomeAssistant,
    entity_id: str,
    *,
    context: Context | None = None,
    auto_resize: bool = False,
) -> tuple[bytes, str | None]:
    """Fetch a snapshot from a camera entity."""
    validate_entity_id_for_domain(entity_id, "camera")
    await _check_user_can_read_entity(hass, context, entity_id)
    try:
        from homeassistant.components.camera import (  # noqa: PLC0415
            async_get_image,
        )
    except ImportError as exc:
        raise HomeAssistantError("Camera component unavailable") from exc

    _LOGGER.debug("Fetching camera snapshot: %s", entity_id)
    try:
        image = await async_get_image(
            hass, entity_id, timeout=_ENTITY_FETCH_TIMEOUT_SECONDS
        )
    except (HomeAssistantError, Unauthorized):
        raise
    except Exception as exc:
        raise HomeAssistantError(
            f"Failed to fetch camera image '{entity_id}': "
            f"{sanitize_log_message(str(exc))}"
        ) from exc
    _check_size(len(image.content), auto_resize=auto_resize)
    return image.content, image.content_type


async def _resolve_image_entity(
    hass: HomeAssistant,
    entity_id: str,
    *,
    context: Context | None = None,
    auto_resize: bool = False,
) -> tuple[bytes, str | None]:
    """Fetch bytes from an HA image entity."""
    validate_entity_id_for_domain(entity_id, "image")
    await _check_user_can_read_entity(hass, context, entity_id)
    try:
        from homeassistant.components.image import (  # noqa: PLC0415
            async_get_image,
        )
    except ImportError as exc:
        raise HomeAssistantError("Image component unavailable") from exc

    _LOGGER.debug("Fetching image entity: %s", entity_id)
    try:
        image = await async_get_image(
            hass, entity_id, timeout=_ENTITY_FETCH_TIMEOUT_SECONDS
        )
    except (HomeAssistantError, Unauthorized):
        raise
    except Exception as exc:
        raise HomeAssistantError(
            f"Failed to fetch image entity '{entity_id}': "
            f"{sanitize_log_message(str(exc))}"
        ) from exc
    _check_size(len(image.content), auto_resize=auto_resize)
    return image.content, image.content_type


async def _stream_to_buffer(
    aiter: Any, max_bytes: int
) -> bytearray:
    """Consume an async byte iterator into a bytearray, aborting on overflow."""
    buf = bytearray()
    async for chunk in aiter:
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise HomeAssistantError(
                f"Image too large (max {max_bytes // (1024 * 1024)}MB) — "
                f"enable auto_resize to allow up to 4x this cap"
            )
    return buf


def _check_content_length(headers: Mapping[str, str], max_bytes: int) -> None:
    raw = headers.get("content-length") or headers.get("Content-Length")
    if raw is None:
        return
    try:
        size = int(raw)
    except (TypeError, ValueError):
        return
    if size > max_bytes:
        raise HomeAssistantError(
            f"Image declared too-large Content-Length ({size}); "
            f"max {max_bytes // (1024 * 1024)}MB — enable auto_resize for "
            f"larger payloads"
        )


async def _resolve_http_httpx(
    hass: HomeAssistant, url: str, *, max_bytes: int
) -> tuple[bytes, str | None]:
    """Fetch via HA's pooled httpx client, walking redirects manually."""
    from homeassistant.helpers.httpx_client import (  # noqa: PLC0415
        get_async_client,
    )
    import httpx  # noqa: PLC0415

    client = get_async_client(hass)
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        validated, _addrs = await validate_image_url_and_resolve(hass, current)
        try:
            async with client.stream(
                "GET",
                validated,
                timeout=httpx.Timeout(
                    _HTTP_TOTAL_TIMEOUT,
                    connect=_HTTP_CONNECT_TIMEOUT,
                    read=_HTTP_READ_TIMEOUT,
                ),
                follow_redirects=False,
            ) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise HomeAssistantError(
                            "HTTP redirect without Location header"
                        )
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                _check_content_length(response.headers, max_bytes)
                buf = await _stream_to_buffer(
                    response.aiter_bytes(), max_bytes
                )
                content_type = response.headers.get("content-type")
                return bytes(buf), content_type
        except HomeAssistantError:
            raise
        except httpx.HTTPError as exc:
            raise HomeAssistantError(
                f"Failed to download image: {sanitize_log_message(str(exc))}"
            ) from exc
    raise HomeAssistantError(
        f"Too many redirects fetching image (>{_MAX_REDIRECTS})"
    )


async def _resolve_http_aiohttp(
    hass: HomeAssistant, url: str, *, max_bytes: int
) -> tuple[bytes, str | None]:
    """Fallback for environments without httpx; uses HA's pooled aiohttp session."""
    from homeassistant.helpers.aiohttp_client import (  # noqa: PLC0415
        async_get_clientsession,
    )

    session = async_get_clientsession(hass)
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        validated, _addrs = await validate_image_url_and_resolve(hass, current)
        try:
            async with session.get(
                validated,
                timeout=aiohttp.ClientTimeout(
                    total=_HTTP_TOTAL_TIMEOUT,
                    connect=_HTTP_CONNECT_TIMEOUT,
                    sock_read=_HTTP_READ_TIMEOUT,
                ),
                allow_redirects=False,
            ) as response:
                if response.status in (301, 302, 303, 307, 308):
                    location = response.headers.get("Location")
                    if not location:
                        raise HomeAssistantError(
                            "HTTP redirect without Location header"
                        )
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                _check_content_length(response.headers, max_bytes)
                buf = await _stream_to_buffer(
                    response.content.iter_chunked(65536), max_bytes
                )
                content_type = response.headers.get("Content-Type")
                return bytes(buf), content_type
        except HomeAssistantError:
            raise
        except aiohttp.ClientError as exc:
            raise HomeAssistantError(
                f"Failed to download image: {sanitize_log_message(str(exc))}"
            ) from exc
    raise HomeAssistantError(
        f"Too many redirects fetching image (>{_MAX_REDIRECTS})"
    )


async def _resolve_http(
    hass: HomeAssistant, url: str, *, auto_resize: bool = False
) -> tuple[bytes, str | None]:
    """Fetch an HTTP/HTTPS image. Validates URL + IPs and streams the body."""
    # Cheap pre-flight: reject obvious junk before resolving DNS.
    validate_image_url(url)
    _LOGGER.debug(
        "Downloading image from URL: %s",
        sanitize_log_message(url),
    )
    max_bytes = _MAX_BYTES_AUTO_RESIZE if auto_resize else _MAX_BYTES
    try:
        import httpx  # noqa: F401, PLC0415
    except ImportError:
        return await _resolve_http_aiohttp(hass, url, max_bytes=max_bytes)
    return await _resolve_http_httpx(hass, url, max_bytes=max_bytes)


async def _resolve_local(
    hass: HomeAssistant, path: str, *, auto_resize: bool = False
) -> tuple[bytes, str | None]:
    """Read a local image file from disk.

    Performs validation, allowlist enforcement, and the actual read
    inside a single executor closure. Symlinks are followed *during*
    validation (via ``Path.resolve(strict=True)``) and rejected if the
    final target is outside ``allowlist_external_dirs`` or fails any
    other check. The file is then opened with ``O_NOFOLLOW`` to defeat
    a TOCTOU symlink swap between validation and open.
    """
    max_bytes = _MAX_BYTES_AUTO_RESIZE if auto_resize else _MAX_BYTES

    def _validate_and_read() -> bytes:
        resolved = _validate_local_path_sync(path, max_bytes=max_bytes)
        is_allowed = hass.config.is_allowed_path
        if not is_allowed(str(resolved)):
            raise HomeAssistantError(
                "Image path is outside Home Assistant's allowlist_external_dirs"
            )
        return open_local_image_no_follow(resolved, max_bytes=max_bytes)

    raw = await hass.async_add_executor_job(_validate_and_read)
    _check_size(len(raw), auto_resize=auto_resize)
    return raw, SOURCE_LOCAL_FILE


def _check_size(num_bytes: int, *, auto_resize: bool = False) -> None:
    """Reject payloads exceeding the configured maximum image size."""
    max_bytes = _MAX_BYTES_AUTO_RESIZE if auto_resize else _MAX_BYTES
    if num_bytes > max_bytes:
        mb = max_bytes // (1024 * 1024)
        hint = (
            ""
            if auto_resize
            else " — enable auto_resize to allow up to 4x this cap"
        )
        raise HomeAssistantError(
            f"Image too large ({num_bytes} bytes; max {mb}MB){hint}"
        )


# ---------------------------------------------------------------------------
# Helpers shared by the service handler and the notify entity.
# ---------------------------------------------------------------------------


# Schema-key → adapter-kwarg. Only ``image_width`` is renamed; the rest
# pass through. Voluptuous fills defaults at validation time, so this
# helper only handles the prefix-strip + the single rename.
_IMAGE_KWARG_RENAME: dict[str, str] = {ATTR_IMAGE_WIDTH: "width"}
_IMAGE_KWARG_KEYS: tuple[str, ...] = (
    ATTR_IMAGE_WIDTH,
    ATTR_ROTATION,
    ATTR_DITHER,
    ATTR_THRESHOLD,
    ATTR_IMPL,
    ATTR_CENTER,
    ATTR_AUTOCONTRAST,
    ATTR_INVERT,
    ATTR_MIRROR,
    ATTR_AUTO_RESIZE,
    ATTR_FALLBACK_IMAGE,
    ATTR_FRAGMENT_HEIGHT,
    ATTR_CHUNK_DELAY_MS,
    ATTR_HIGH_DENSITY,
)


def extract_image_kwargs(
    data: Mapping[str, Any],
    printer_defaults: Mapping[str, Any],
    *,
    prefix: str = "",
) -> dict[str, Any]:
    """Pull the print_image kwargs from a service-call/notify-call dict.

    ``prefix`` is empty for the service-call form and ``"image_"`` for
    the notify entity. ``ATTR_IMAGE`` and ``ATTR_IMAGE_WIDTH`` are
    never prefixed (both are already namespaced). Only keys present
    in ``data`` are included — missing keys fall through to the
    adapter's signature defaults.

    For the notify form, an unprefixed key wins over the prefixed
    variant ONLY if the unprefixed key is unique to the image options
    (e.g. ``dither``, ``threshold``, ``rotation``). This collapses the
    historic ``image_dither`` / ``dither`` confusion without breaking
    existing callers.
    """
    def k(name: str) -> str:
        if not prefix or name in (ATTR_IMAGE, ATTR_IMAGE_WIDTH):
            return name
        return f"{prefix}{name}"

    # Keys that are unique to the image fragment — safe to also accept
    # unprefixed even when the prefix is "image_". (We deliberately
    # exclude ATTR_ALIGN / ATTR_HIGH_DENSITY here because they clash
    # with text-side fields on the notify entity.)
    image_only_unprefixed = {
        ATTR_ROTATION,
        ATTR_DITHER,
        ATTR_THRESHOLD,
        ATTR_IMPL,
        ATTR_CENTER,
        ATTR_AUTOCONTRAST,
        ATTR_INVERT,
        ATTR_MIRROR,
        ATTR_AUTO_RESIZE,
        ATTR_FALLBACK_IMAGE,
        ATTR_FRAGMENT_HEIGHT,
        ATTR_CHUNK_DELAY_MS,
    }

    out: dict[str, Any] = {ATTR_IMAGE: data.get(ATTR_IMAGE)}
    out[ATTR_ALIGN] = data.get(k(ATTR_ALIGN)) or printer_defaults.get("align")
    for key in _IMAGE_KWARG_KEYS:
        prefixed = k(key)
        if prefixed in data:
            out[_IMAGE_KWARG_RENAME.get(key, key)] = data[prefixed]
        elif prefix and key in image_only_unprefixed and key in data:
            out[_IMAGE_KWARG_RENAME.get(key, key)] = data[key]
    return out


__all__ = [
    "SOURCE_DATA_URI",
    "SOURCE_LOCAL_FILE",
    "SourceKind",
    "classify_source",
    "extract_image_kwargs",
    "render_template",
    "resolve_image_bytes",
]
