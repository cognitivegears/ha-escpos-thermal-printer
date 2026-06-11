"""Tests for ``printer.image_operations._resolve_with_retry`` (T-L1 / P-M4).

The retry path retries once on transient camera/http failure with a
0.5 s back-off — but skips that back-off when the original error was
a timeout (an upstream that took >10 s to respond is "not ready",
not "transiently slow"; another 0.5 s won't help). This module pins
both the timeout-skip and the back-off-fires-otherwise paths.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest


async def test_resolve_with_retry_skips_backoff_on_timeout(hass):  # type: ignore[no-untyped-def]
    """P-M4: TimeoutError must NOT trigger the 0.5s back-off retry.

    Asserts the sleep is never called when the primary fails with a
    timeout — straight to the fallback (or re-raise).
    """
    from custom_components.escpos_printer.printer import image_operations

    call_count = 0

    async def _resolve(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        # Raise a HomeAssistantError whose `__cause__` is a TimeoutError;
        # `_is_timeout_cause` walks the cause chain.
        try:
            raise TimeoutError("HTTP timeout after 10s")
        except TimeoutError as exc:
            raise HomeAssistantError("download failed") from exc

    sleep_mock = AsyncMock()
    with (
        patch.object(image_operations, "resolve_image_bytes", side_effect=_resolve),
        patch("asyncio.sleep", new=sleep_mock),
    ):
        with pytest.raises(HomeAssistantError):
            await image_operations._resolve_with_retry(
                hass,
                "https://example.com/x.png",
                context=None,
                auto_resize=False,
                fallback=None,
            )

    assert call_count == 1, "must NOT retry on timeout"
    sleep_mock.assert_not_called()


async def test_resolve_with_retry_does_retry_on_non_timeout(hass):  # type: ignore[no-untyped-def]
    """P-M4: a non-timeout transient failure DOES trigger the back-off retry."""
    from custom_components.escpos_printer.printer import image_operations

    call_count = 0

    async def _resolve(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        nonlocal call_count
        call_count += 1
        raise HomeAssistantError("camera image temporarily unavailable")

    sleep_mock = AsyncMock()
    with (
        patch.object(image_operations, "resolve_image_bytes", side_effect=_resolve),
        patch("asyncio.sleep", new=sleep_mock),
    ):
        with pytest.raises(HomeAssistantError):
            await image_operations._resolve_with_retry(
                hass,
                "https://example.com/x.png",
                context=None,
                auto_resize=False,
                fallback=None,
            )

    # 2 calls = initial + retry
    assert call_count == 2, "must retry once on non-timeout transient failure"
    sleep_mock.assert_called_once_with(0.5)


async def test_resolve_with_retry_threads_allow_local(hass):  # type: ignore[no-untyped-def]
    """G2: allow_local must reach the primary, retry, AND fallback resolve calls.

    A regression dropping `allow_local=` from any of the three forwarding
    sites would silently downgrade a LAN URL to strict validation on the
    retry/fallback — exactly the transient-camera case retry exists for.
    """
    from custom_components.escpos_printer.printer import image_operations

    seen: list[object] = []

    async def _resolve(_hass, _img, **kwargs):  # type: ignore[no-untyped-def]
        seen.append(kwargs.get("allow_local"))
        raise HomeAssistantError("boom")  # force retry + fallback

    with (
        patch.object(image_operations, "resolve_image_bytes", side_effect=_resolve),
        patch("asyncio.sleep", new=AsyncMock()),
    ):
        with pytest.raises(HomeAssistantError):
            await image_operations._resolve_with_retry(
                hass,
                "http://192.168.1.5/x.png",
                context=None,
                auto_resize=False,
                fallback="http://192.168.1.6/y.png",
                allow_local=True,
            )

    # primary + retry + fallback — every attempt must carry the relaxed flag.
    assert seen, "resolve_image_bytes was never called"
    assert all(v is True for v in seen), f"allow_local not threaded on every attempt: {seen}"


async def test_prepare_image_for_print_reads_adapter_allow_local(hass):  # type: ignore[no-untyped-def]
    """G3: prepare_image_for_print must read host.allow_local_image_urls and thread it.

    This is the config->adapter->resolver handoff. A typo'd attribute name
    would make getattr silently yield False and the feature would be dead
    while every endpoint test still passed.
    """
    import io

    from PIL import Image

    from custom_components.escpos_printer.printer import image_operations

    def _png() -> bytes:
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), color=(0, 0, 0)).save(buf, format="PNG")
        return buf.getvalue()

    host = MagicMock()
    host.allow_local_image_urls = True
    host.get_profile_pixel_width.return_value = 384
    host.reliability_profile_defaults = {}
    host.default_chunk_delay_ms = 0
    host._image_stats = None

    seen: dict[str, object] = {}

    async def _capture(_hass, _img, **kwargs):  # type: ignore[no-untyped-def]
        seen.update(kwargs)
        return _png(), "image/png"

    with patch.object(image_operations, "_resolve_with_retry", side_effect=_capture):
        await image_operations.prepare_image_for_print(
            host, hass, "http://192.168.1.5/x.png"
        )

    assert seen.get("allow_local") is True


def test_is_timeout_cause_walks_chain():  # type: ignore[no-untyped-def]
    """The helper must recognise a wrapped TimeoutError anywhere in the chain."""
    from custom_components.escpos_printer.printer.image_operations import (
        _is_timeout_cause,
    )

    # Direct TimeoutError
    assert _is_timeout_cause(TimeoutError("direct"))

    # Wrapped in HomeAssistantError via __cause__ — build the chain
    # manually rather than via try/except to keep ruff PT017 happy.
    inner = TimeoutError("inner")
    outer = HomeAssistantError("outer")
    outer.__cause__ = inner
    assert _is_timeout_cause(outer)

    # Plain RuntimeError shouldn't match.
    assert not _is_timeout_cause(RuntimeError("nope"))
