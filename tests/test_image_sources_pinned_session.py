"""Direct unit tests for the DNS-pinning machinery in ``image_sources``.

The end-to-end HTTP tests in ``test_image_sources.py`` cover the happy
fetch path, but they don't exercise the defensive branches in
:class:`_StaticResolver` (hostname mismatch, family mismatch, malformed
addresses) or the trivial helpers :func:`_build_pinned_session` /
:func:`_check_size`. These tests target each branch directly so the
SSRF / DNS-rebinding defenses don't drift uncovered.
"""

from __future__ import annotations

import socket

import aiohttp
from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.escpos_printer.image_sources import (
    _build_pinned_session,
    _check_size,
    _StaticResolver,
)


def test_static_resolver_buckets_ipv4_and_ipv6_addresses() -> None:
    resolver = _StaticResolver("example.com", ["192.0.2.1", "2001:db8::1"])
    assert resolver._addrs_by_family[socket.AF_INET] == ["192.0.2.1"]
    assert resolver._addrs_by_family[socket.AF_INET6] == ["2001:db8::1"]


def test_static_resolver_skips_malformed_addresses() -> None:
    # ValueError-in-init path: an unparseable address must not crash
    # the constructor, just be dropped. The valid address still routes.
    resolver = _StaticResolver("example.com", ["not-an-ip", "192.0.2.1"])
    assert resolver._addrs_by_family[socket.AF_INET] == ["192.0.2.1"]
    assert resolver._addrs_by_family[socket.AF_INET6] == []


@pytest.mark.asyncio
async def test_static_resolver_rejects_unexpected_hostname() -> None:
    resolver = _StaticResolver("example.com", ["192.0.2.1"])
    with pytest.raises(OSError, match="not pre-validated"):
        await resolver.resolve("evil.example", port=80, family=socket.AF_INET)


@pytest.mark.asyncio
async def test_static_resolver_rejects_unsupported_family() -> None:
    # IPv4-only address set; an IPv6 connect attempt must be rejected
    # rather than silently returning an empty list.
    resolver = _StaticResolver("example.com", ["192.0.2.1"])
    with pytest.raises(OSError, match="no pre-validated addresses"):
        await resolver.resolve("example.com", port=80, family=socket.AF_INET6)


@pytest.mark.asyncio
async def test_static_resolver_resolves_default_af_unspec_family() -> None:
    # Regression (issue #95): ``aiohttp.TCPConnector`` resolves with
    # ``family=AF_UNSPEC`` (0) by default — it does NOT split the lookup
    # per family. The old ``get(family, [])`` filter only knew AF_INET /
    # AF_INET6 buckets, so the default lookup matched neither bucket and
    # every HTTP/HTTPS image fetch died with
    # ``Cannot connect to host <host> ssl:default [None]``. AF_UNSPEC must
    # mean "any pre-validated address", each tagged with its real family.
    resolver = _StaticResolver("example.com", ["192.0.2.1", "2001:db8::1"])
    out = await resolver.resolve("example.com", port=443, family=socket.AF_UNSPEC)
    by_family = {entry["family"]: entry["host"] for entry in out}
    assert by_family == {
        socket.AF_INET: "192.0.2.1",
        socket.AF_INET6: "2001:db8::1",
    }
    for entry in out:
        assert entry["hostname"] == "example.com"
        assert entry["port"] == 443


@pytest.mark.asyncio
async def test_static_resolver_af_unspec_with_ipv4_only() -> None:
    # AF_UNSPEC lookup against an IPv4-only pin must still succeed and
    # tag the result AF_INET (not the requested AF_UNSPEC).
    resolver = _StaticResolver("example.com", ["192.0.2.1"])
    out = await resolver.resolve("example.com", port=80, family=socket.AF_UNSPEC)
    assert len(out) == 1
    assert out[0]["host"] == "192.0.2.1"
    assert out[0]["family"] == socket.AF_INET


@pytest.mark.asyncio
async def test_static_resolver_af_unspec_with_no_valid_addresses_raises() -> None:
    # Defense intact: if nothing pre-validated, even an AF_UNSPEC lookup
    # must raise rather than hand the connector an empty address set.
    resolver = _StaticResolver("example.com", ["not-an-ip"])
    with pytest.raises(OSError, match="no pre-validated addresses"):
        await resolver.resolve("example.com", port=443, family=socket.AF_UNSPEC)


@pytest.mark.asyncio
async def test_build_pinned_session_connector_resolves_with_af_unspec() -> None:
    # Locks in the assumption behind issue #95: the connector built for
    # the actual fetch uses ``family=AF_UNSPEC``, so that is the value the
    # resolver must handle. If a future aiohttp changes this default, this
    # guard fires and tells us to revisit the resolver contract.
    session = _build_pinned_session("example.com", ["192.0.2.1"])
    try:
        connector = session.connector
        assert connector is not None
        assert connector._family == socket.AF_UNSPEC
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_static_resolver_returns_aiohttp_shaped_address_dicts() -> None:
    resolver = _StaticResolver("example.com", ["192.0.2.1", "192.0.2.2"])
    out = await resolver.resolve("example.com", port=443, family=socket.AF_INET)
    assert len(out) == 2
    for entry in out:
        assert entry["hostname"] == "example.com"
        assert entry["port"] == 443
        assert entry["family"] == socket.AF_INET
        assert entry["proto"] == 0
        assert entry["flags"] == 0
    assert {entry["host"] for entry in out} == {"192.0.2.1", "192.0.2.2"}


@pytest.mark.asyncio
async def test_static_resolver_close_is_noop() -> None:
    # Required by the AbstractResolver contract but we hold no real
    # resources — confirm it's safe to call. Bind the await separately
    # so the assertion is pure (CodeQL py/side-effect-in-assert: asserts
    # are stripped under ``python -O`` and must not perform real work).
    resolver = _StaticResolver("example.com", ["192.0.2.1"])
    result = await resolver.close()
    assert result is None


@pytest.mark.asyncio
async def test_build_pinned_session_returns_session_with_pinned_resolver() -> None:
    # aiohttp.TCPConnector grabs the running event loop on init, so this
    # has to run inside one.
    session = _build_pinned_session("example.com", ["192.0.2.1"])
    try:
        assert isinstance(session, aiohttp.ClientSession)
        # The underlying connector must carry our resolver, not the
        # default threaded resolver — that's the entire S-H1 defense.
        connector = session.connector
        assert connector is not None
        assert isinstance(connector._resolver, _StaticResolver)
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_build_pinned_session_sends_identifying_headers() -> None:
    # The bare per-request session must not fall back to aiohttp's default
    # ``Python/3.x aiohttp/…`` User-Agent — CDN/WAF bot rules answer that
    # with HTML block pages served as 200, which then die in the image
    # decoder. HA's own UA (as sent by the pooled clients pre-0.7.x) plus
    # an image-biased Accept header restore the identity that worked.
    session = _build_pinned_session("example.com", ["192.0.2.1"])
    try:
        assert "HomeAssistant" in session.headers["User-Agent"]
        assert session.headers["Accept"].startswith("image/")
        # AVIF decode support is optional (pillow-heif); don't invite it.
        assert "avif" not in session.headers["Accept"].lower()
    finally:
        await session.close()


def test_check_size_below_max_returns_silently() -> None:
    # 1 byte is well under any plausible cap.
    _check_size(1, auto_resize=False)
    _check_size(1, auto_resize=True)


def test_check_size_over_cap_raises_with_auto_resize_hint() -> None:
    # 64 MB is over the non-auto-resize cap; expect the hint that
    # auto_resize is available.
    huge = 64 * 1024 * 1024
    with pytest.raises(HomeAssistantError, match="enable auto_resize") as exc:
        _check_size(huge, auto_resize=False)
    assert "Image too large" in str(exc.value)


def test_check_size_over_auto_resize_cap_omits_hint() -> None:
    # Way beyond the 4x cap. The error message must NOT suggest
    # auto_resize since that's already enabled.
    huge = 1024 * 1024 * 1024  # 1 GB
    with pytest.raises(HomeAssistantError) as exc:
        _check_size(huge, auto_resize=True)
    assert "enable auto_resize" not in str(exc.value)
    assert "Image too large" in str(exc.value)
