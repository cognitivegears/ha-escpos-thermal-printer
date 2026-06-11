"""Unit tests for the multi-source image resolver.

Tests fall into two groups:

1. Happy paths (data URI, camera/image entity, HTTP, local file).
2. Regression tests pinning Phase 2 security fixes from
   `.full-review/05-final-report.md`: SSRF private-IP rejection,
   symlink rejection, allowlist enforcement, authorization checks,
   slow-loris cap, fallback-bug masking.
"""

from __future__ import annotations

import asyncio
import base64
import io
import socket
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError, Unauthorized
from PIL import Image
import pytest

from custom_components.escpos_printer.image_sources import (
    SOURCE_DATA_URI,
    SOURCE_LOCAL_FILE,
    classify_source,
    resolve_image_bytes,
)


def _install_fake_camera_module(monkeypatch: pytest.MonkeyPatch, func) -> None:  # type: ignore[no-untyped-def]
    mod = types.ModuleType("homeassistant.components.camera")
    mod.async_get_image = func  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.components.camera", mod)


def _install_fake_image_module(monkeypatch: pytest.MonkeyPatch, func) -> None:  # type: ignore[no-untyped-def]
    mod = types.ModuleType("homeassistant.components.image")
    mod.async_get_image = func  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "homeassistant.components.image", mod)


def _png_bytes(width: int = 8, height: int = 8) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color=(255, 0, 0)).save(buf, format="PNG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Classification (T-L6: SOURCE_* constants are exported).
# ---------------------------------------------------------------------------


def test_classify_source_table():  # type: ignore[no-untyped-def]
    assert classify_source("data:image/png;base64,AAAA")[0] == "data"
    assert classify_source("camera.front_door")[0] == "camera"
    assert classify_source("image.weather_map")[0] == "image"
    assert classify_source("https://example.com/x.png")[0] == "http"
    assert classify_source("/config/www/logo.png")[0] == "local"


# ---------------------------------------------------------------------------
# Happy paths.
# ---------------------------------------------------------------------------


async def test_resolve_local_path(hass, tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    img = tmp_path / "logo.png"
    img.write_bytes(_png_bytes())
    monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: True)
    raw, hint = await resolve_image_bytes(hass, str(img))
    assert raw == img.read_bytes()
    assert hint == SOURCE_LOCAL_FILE


async def test_resolve_local_path_missing_raises(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError, match="does not exist"):
        await resolve_image_bytes(hass, "/nope/missing.png")


async def test_resolve_base64_data_uri(hass):  # type: ignore[no-untyped-def]
    raw = _png_bytes()
    encoded = base64.b64encode(raw).decode()
    src = f"data:image/png;base64,{encoded}"
    result, hint = await resolve_image_bytes(hass, src)
    assert result == raw
    assert hint == SOURCE_DATA_URI


async def test_resolve_base64_rejects_non_data_uri(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError, match="data:image"):
        await resolve_image_bytes(hass, "data:text/plain;base64,aGVsbG8=")


async def test_resolve_camera_uses_async_get_image(hass, monkeypatch):  # type: ignore[no-untyped-def]
    raw = _png_bytes()
    fake = type("Img", (), {"content": raw, "content_type": "image/png"})()
    mock = AsyncMock(return_value=fake)
    _install_fake_camera_module(monkeypatch, mock)
    result, hint = await resolve_image_bytes(hass, "camera.front_door")
    assert result == raw
    assert hint == "image/png"
    mock.assert_awaited_once()


async def test_resolve_camera_rejects_wrong_domain(hass):  # type: ignore[no-untyped-def]
    # T-L1: tighten match — exact error format.
    with pytest.raises(HomeAssistantError, match="domain 'camera'"):
        await resolve_image_bytes(hass, "camera.")


async def test_resolve_image_entity_uses_async_get_image(hass, monkeypatch):  # type: ignore[no-untyped-def]
    raw = _png_bytes()
    fake = type("Img", (), {"content": raw, "content_type": "image/png"})()
    mock = AsyncMock(return_value=fake)
    _install_fake_image_module(monkeypatch, mock)
    result, _ = await resolve_image_bytes(hass, "image.weather_map")
    assert result == raw
    mock.assert_awaited_once()


async def test_oversized_base64_rejected(hass):  # type: ignore[no-untyped-def]
    big = base64.b64encode(b"\x00" * (11 * 1024 * 1024)).decode()
    with pytest.raises(HomeAssistantError, match="too large"):
        await resolve_image_bytes(hass, f"data:image/png;base64,{big}")


async def test_empty_source_rejected(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError, match="non-empty"):
        await resolve_image_bytes(hass, "   ")


# ---------------------------------------------------------------------------
# T-C2: Local-file symlink + allowlist regression tests.
# ---------------------------------------------------------------------------


async def test_resolve_local_path_rejects_symlink_outside_allowlist(  # type: ignore[no-untyped-def]
    hass, tmp_path, monkeypatch, make_symlink
):
    """A symlink whose resolved target is outside the allowlist must be rejected."""
    # Target has a valid `.png` extension so the symlink survives the
    # extension check; the allowlist check then rejects on resolved path.
    target = tmp_path / "secret.png"
    target.write_bytes(_png_bytes())
    link = make_symlink(target, link_name="logo.png")
    # Allowlist denies anything ending in `secret.png`, which is what the
    # symlink resolves to.
    monkeypatch.setattr(
        hass.config,
        "is_allowed_path",
        lambda p: "secret.png" not in str(p),
    )
    with pytest.raises(HomeAssistantError, match="allowlist"):
        await resolve_image_bytes(hass, str(link))


async def test_resolve_local_path_respects_allowlist(  # type: ignore[no-untyped-def]
    hass, tmp_path, monkeypatch
):
    """Path outside `allowlist_external_dirs` must raise (no warn-but-read)."""
    img = tmp_path / "logo.png"
    img.write_bytes(_png_bytes())
    monkeypatch.setattr(hass.config, "is_allowed_path", lambda _p: False)
    with pytest.raises(HomeAssistantError, match="allowlist"):
        await resolve_image_bytes(hass, str(img))


# ---------------------------------------------------------------------------
# T-C1: SSRF regression — private/loopback/link-local rejected at validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "addr",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "172.16.0.1",
        "169.254.169.254",
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
async def test_resolve_http_rejects_private_resolved_address(  # type: ignore[no-untyped-def]
    hass, monkeypatch, addr
):
    """``getaddrinfo`` returning a private IP must cause refusal."""

    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        family = socket.AF_INET6 if ":" in addr else socket.AF_INET
        return [(family, socket.SOCK_STREAM, 0, "", (addr, 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HomeAssistantError, match="non-public address"):
        await resolve_image_bytes(hass, "https://example.com/x.png")


async def test_resolve_http_strict_error_hints_at_option(  # type: ignore[no-untyped-def]
    hass, monkeypatch
):
    """The strict-mode rejection must point the user at the opt-in toggle."""

    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HomeAssistantError, match="Allow local image URLs"):
        await resolve_image_bytes(hass, "https://example.com/x.png")


async def test_resolve_http_allows_private_with_allow_local(  # type: ignore[no-untyped-def]
    hass, monkeypatch, mock_pooled_aiohttp
):
    """``allow_local=True`` lets a private/LAN address resolve and fetch."""

    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("192.168.1.50", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    def _factory():  # type: ignore[no-untyped-def]
        from tests.conftest import fake_aiohttp_response

        return fake_aiohttp_response(
            status=200, headers={"Content-Type": "image/png"}, chunks=[_png_bytes()]
        )

    mock_pooled_aiohttp(_factory)
    raw, content_type = await resolve_image_bytes(
        hass, "https://camera.local/snapshot.png", allow_local=True
    )
    assert raw == _png_bytes()
    assert content_type == "image/png"


async def test_resolve_http_allow_local_still_blocks_metadata(  # type: ignore[no-untyped-def]
    hass, monkeypatch
):
    """Even with ``allow_local=True`` the cloud-metadata endpoint stays blocked."""

    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("169.254.169.254", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)
    with pytest.raises(HomeAssistantError, match="blocked address"):
        await resolve_image_bytes(
            hass, "https://metadata.example/latest/meta-data/", allow_local=True
        )


async def test_resolve_http_rejects_non_default_port(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError, match="port"):
        await resolve_image_bytes(hass, "https://example.com:22/x.png")


async def test_resolve_http_rejects_url_credentials(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError, match="credentials"):
        await resolve_image_bytes(hass, "https://user:pass@example.com/x.png")


async def test_resolve_http_rejects_idn_punycode(hass):  # type: ignore[no-untyped-def]
    with pytest.raises(HomeAssistantError, match="IDN"):
        await resolve_image_bytes(hass, "https://xn--80ak6aa92e.com/x.png")


# ---------------------------------------------------------------------------
# T-C3: Camera authorization check.
# ---------------------------------------------------------------------------


async def test_resolve_camera_denied_for_restricted_user(  # type: ignore[no-untyped-def]
    hass, monkeypatch, restricted_user_context
):
    """A user without POLICY_READ on the camera must receive Unauthorized."""
    fake = type("Img", (), {"content": _png_bytes(), "content_type": "image/png"})()
    _install_fake_camera_module(monkeypatch, AsyncMock(return_value=fake))
    context = await restricted_user_context(hass, ["camera.front_door"])
    with pytest.raises(Unauthorized):
        await resolve_image_bytes(hass, "camera.front_door", context=context)


# ---------------------------------------------------------------------------
# T-H5: Slow-loris harness — the streaming cap aborts on oversize.
# ---------------------------------------------------------------------------


async def test_resolve_http_aiohttp_streams_with_cap(  # type: ignore[no-untyped-def]
    hass, monkeypatch, mock_pooled_aiohttp
):
    """Streaming reader must abort once it has consumed more than the cap."""
    # Force the aiohttp fallback path by hiding httpx.
    monkeypatch.setitem(sys.modules, "httpx", None)

    # Allow the URL to validate.
    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    big_chunks = [b"\x00" * (1024 * 1024)] * 12  # 12 MB > 10 MB cap

    def _factory():  # type: ignore[no-untyped-def]
        from tests.conftest import fake_aiohttp_response

        return fake_aiohttp_response(
            status=200, headers={"Content-Type": "image/png"}, chunks=big_chunks
        )

    mock_pooled_aiohttp(_factory)
    with pytest.raises(HomeAssistantError, match="too large"):
        await resolve_image_bytes(hass, "https://example.com/x.png")


async def test_resolve_http_aiohttp_honors_content_length(  # type: ignore[no-untyped-def]
    hass, monkeypatch, mock_pooled_aiohttp
):
    """Declared-too-large Content-Length must be rejected before reading."""
    monkeypatch.setitem(sys.modules, "httpx", None)

    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    def _factory():  # type: ignore[no-untyped-def]
        from tests.conftest import fake_aiohttp_response

        return fake_aiohttp_response(
            status=200,
            headers={
                "Content-Type": "image/png",
                "Content-Length": str(100 * 1024 * 1024),
            },
            chunks=[b""],
        )

    mock_pooled_aiohttp(_factory)
    with pytest.raises(HomeAssistantError, match="too-large"):
        await resolve_image_bytes(hass, "https://example.com/x.png")


# ---------------------------------------------------------------------------
# S-H1: HTTP fetch is DNS-rebinding-safe (always uses aiohttp with pinned
# resolver; httpx fast-path was removed).
# ---------------------------------------------------------------------------


async def test_resolve_http_http_error_propagates_as_ha_error(  # type: ignore[no-untyped-def]
    hass, monkeypatch, mock_pooled_aiohttp
):
    """A 4xx from the fetch must surface as HomeAssistantError, not bubble."""

    def fake_getaddrinfo(_host, _port, **_kw):  # type: ignore[no-untyped-def]
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr("socket.getaddrinfo", fake_getaddrinfo)

    import aiohttp as _aiohttp

    def _factory():  # type: ignore[no-untyped-def]
        from tests.conftest import fake_aiohttp_response

        resp = fake_aiohttp_response()

        def _raise():  # type: ignore[no-untyped-def]
            raise _aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=404,
                message="Not Found",
            )

        resp.raise_for_status = _raise
        return resp

    mock_pooled_aiohttp(_factory)
    with pytest.raises(HomeAssistantError, match="download image"):
        await resolve_image_bytes(hass, "https://example.com/x.png")


async def test_static_resolver_rejects_unrelated_hostname(  # type: ignore[no-untyped-def]
    hass,
):
    """The pinned resolver must refuse lookups for hostnames it was not built for.

    Defense against a redirect to a different host: even if validation
    is bypassed, the connector-level resolver only knows the originally
    pinned hostname.
    """
    from custom_components.escpos_printer.image_sources import _StaticResolver

    resolver = _StaticResolver("example.com", ["93.184.216.34"])
    with pytest.raises(OSError, match="pre-validated"):
        await resolver.resolve("evil.example", port=443)


async def test_static_resolver_returns_pinned_address(  # type: ignore[no-untyped-def]
    hass,
):
    """The pinned resolver returns only the pre-validated address for its host."""
    from custom_components.escpos_printer.image_sources import _StaticResolver

    resolver = _StaticResolver("example.com", ["93.184.216.34"])
    infos = await resolver.resolve("example.com", port=443)
    assert len(infos) == 1
    assert infos[0]["host"] == "93.184.216.34"


# ---------------------------------------------------------------------------
# T-M8: Content-type hint propagation (sentinel constants, not raw header).
# ---------------------------------------------------------------------------


def test_source_sentinels_are_stable():  # type: ignore[no-untyped-def]
    assert SOURCE_DATA_URI == "data-uri"
    assert SOURCE_LOCAL_FILE == "local-file"


# Keep asyncio import alive for `asyncio.sleep` usage if added later.
_ = asyncio
_ = MagicMock
