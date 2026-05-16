"""Tests for chunked image transmission with inter-chunk delays (issues #45/#43)."""

from __future__ import annotations

import asyncio
import time
import tracemalloc
from unittest.mock import MagicMock, patch

from PIL import Image
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN


async def _setup_entry(hass):  # type: ignore[no-untyped-def]
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


def _allow_all(hass):  # type: ignore[no-untyped-def]
    """Make `hass.config.is_allowed_path` always permit (test convenience)."""
    hass.config.is_allowed_path = lambda _p: True  # type: ignore[assignment]


async def test_tall_image_is_split_into_chunks(hass, tmp_path):  # type: ignore[no-untyped-def]
    """A 1000px tall image with fragment_height=256 should produce 4 chunks."""
    await _setup_entry(hass)
    _allow_all(hass)

    img_path = tmp_path / "tall.png"
    Image.new("L", (300, 1000), color=200).save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {
                "image": str(img_path),
                "fragment_height": 256,
                "chunk_delay_ms": 0,  # no delay so test is fast
            },
            blocking=True,
        )
    # 1000 / 256 = 4 chunks (3 of height 256 + 1 of height 232)
    assert fake.image.call_count == 4


async def test_chunk_delay_sleeps_between_chunks(hass, tmp_path):  # type: ignore[no-untyped-def]
    """A 4-chunk image with 50ms delay should take at least 3 * 50ms = 150ms.

    T-L3: patches ``asyncio.sleep`` to record durations exactly rather than
    relying on wall-clock timing (flaky under CI load).
    """
    await _setup_entry(hass)
    _allow_all(hass)

    img_path = tmp_path / "tall.png"
    Image.new("L", (300, 1000), color=200).save(img_path)

    recorded: list[float] = []
    real_sleep = asyncio.sleep

    async def _record_sleep(delay: float, *args, **kwargs):  # type: ignore[no-untyped-def]
        if delay > 0:
            recorded.append(delay)
        # Call through with 0 so the test stays fast.
        await real_sleep(0, *args, **kwargs)

    fake = MagicMock()
    with (
        patch("escpos.printer.Network", return_value=fake),
        patch(
            "custom_components.escpos_printer.printer.image_operations.asyncio.sleep",
            _record_sleep,
        ),
    ):
        start = time.perf_counter()
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {
                "image": str(img_path),
                "fragment_height": 256,
                "chunk_delay_ms": 50,
            },
            blocking=True,
        )
        elapsed = time.perf_counter() - start
    # 3 chunk boundaries between 4 chunks → 3 sleeps of 50ms.
    assert recorded == [0.05, 0.05, 0.05], recorded
    assert fake.image.call_count == 4
    # Sanity: we didn't actually wait 150ms.
    assert elapsed < 1.0


async def test_short_image_not_chunked(hass, tmp_path):  # type: ignore[no-untyped-def]
    """An image shorter than fragment_height is sent as a single call."""
    await _setup_entry(hass)
    _allow_all(hass)

    img_path = tmp_path / "short.png"
    Image.new("L", (300, 100), color=200).save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {"image": str(img_path), "fragment_height": 256, "chunk_delay_ms": 0},
            blocking=True,
        )
    assert fake.image.call_count == 1


async def test_print_image_with_dither_and_impl(hass, tmp_path):  # type: ignore[no-untyped-def]
    """New parameters (dither, impl) are passed through to python-escpos.

    T-L4: also assert ``fragment_height`` arrives, which detects the
    ``TypeError`` fallback path — if the kwarg-rich `printer.image()`
    call ever starts raising, the test pins that we silently fell
    back to the kwarg-less form.
    """
    await _setup_entry(hass)
    _allow_all(hass)

    img_path = tmp_path / "logo.png"
    Image.new("L", (200, 100), color=128).save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        await hass.services.async_call(
            DOMAIN,
            "print_image",
            {
                "image": str(img_path),
                "dither": "threshold",
                "threshold": 100,
                "impl": "graphics",
                "center": True,
            },
            blocking=True,
        )
    assert fake.image.called
    call_kwargs = fake.image.call_args.kwargs
    assert call_kwargs.get("impl") == "graphics"
    assert call_kwargs.get("center") is True
    # `fragment_height` arrives — proves we didn't hit the TypeError fallback.
    assert "fragment_height" in call_kwargs


async def test_invalid_dither_rejected(hass, tmp_path):  # type: ignore[no-untyped-def]
    """Unknown dither mode is rejected at the schema layer (BP-C1).

    Voluptuous fails before the handler runs, so no printer I/O happens.
    """
    await _setup_entry(hass)
    _allow_all(hass)
    img_path = tmp_path / "x.png"
    Image.new("L", (10, 10)).save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        with pytest.raises(Exception):
            await hass.services.async_call(
                DOMAIN,
                "print_image",
                {"image": str(img_path), "dither": "garbage"},
                blocking=True,
            )
    assert not fake.image.called


async def test_invalid_impl_rejected(hass, tmp_path):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    _allow_all(hass)
    img_path = tmp_path / "x.png"
    Image.new("L", (10, 10)).save(img_path)

    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        with pytest.raises(Exception):
            await hass.services.async_call(
                DOMAIN,
                "print_image",
                {"image": str(img_path), "impl": "no_such_impl"},
                blocking=True,
            )


# ---------------------------------------------------------------------------
# T-H7: cancellation cleanup — paper is cut even when print_image is
# cancelled mid-loop.
# ---------------------------------------------------------------------------


async def test_cancellation_mid_print_still_cuts(hass, tmp_path):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    _allow_all(hass)

    img_path = tmp_path / "tall.png"
    Image.new("L", (300, 1000), color=200).save(img_path)

    fake = MagicMock()
    # Cancel the task on the second `image()` call.
    cancel_after = {"n": 0}
    task_ref: dict[str, asyncio.Task] = {}

    def _maybe_cancel(*_a, **_kw):  # type: ignore[no-untyped-def]
        cancel_after["n"] += 1
        if cancel_after["n"] >= 2 and "task" in task_ref:
            task_ref["task"].cancel()

    fake.image.side_effect = _maybe_cancel

    with patch("escpos.printer.Network", return_value=fake):
        task = asyncio.create_task(
            hass.services.async_call(
                DOMAIN,
                "print_image",
                {
                    "image": str(img_path),
                    "fragment_height": 256,
                    "chunk_delay_ms": 1,
                    "cut": "full",
                    "feed": 3,
                },
                blocking=True,
            )
        )
        task_ref["task"] = task
        with pytest.raises((asyncio.CancelledError, Exception)):
            await task

    # Best-effort cleanup must invoke cut so the paper isn't left hanging.
    assert fake.cut.called


# ---------------------------------------------------------------------------
# T-H6: memory regression for tall images (lazy slicing + bounded peaks).
# ---------------------------------------------------------------------------


async def test_tall_image_memory_under_budget(hass, tmp_path):  # type: ignore[no-untyped-def]
    """A tall image must stay under a coarse memory ceiling (tracemalloc)."""
    await _setup_entry(hass)
    _allow_all(hass)

    img_path = tmp_path / "tall.png"
    # 1x4000 PNG is well under 1 MB on disk; without lazy slicing the
    # adapter would materialise ~16 cropped surfaces.
    Image.new("L", (300, 4000), color=200).save(img_path)

    fake = MagicMock()
    tracemalloc.start()
    try:
        with patch("escpos.printer.Network", return_value=fake):
            await hass.services.async_call(
                DOMAIN,
                "print_image",
                {
                    "image": str(img_path),
                    "fragment_height": 256,
                    "chunk_delay_ms": 0,
                },
                blocking=True,
            )
        _current, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    # ≤80 MB peak across the whole print_image flow is generous on
    # a Pi-class host (raw image ≈ 1 MB, surface ≈ 1 MB, slices ≈ 1 MB).
    assert peak < 80 * 1024 * 1024, f"peak {peak / 1024 / 1024:.1f} MB too high"


# ---------------------------------------------------------------------------
# MAX_SLICES guardrail.
# ---------------------------------------------------------------------------


async def test_max_slices_cap_rejects_pathological_input(hass, tmp_path):  # type: ignore[no-untyped-def]
    await _setup_entry(hass)
    _allow_all(hass)
    img_path = tmp_path / "ribbon.png"
    # 16-px wide x 5000-px tall, fragment_height=16 =&gt; 313 slices > MAX_SLICES.
    # This should refuse the print rather than burn paper.
    Image.new("L", (16, 5000), color=128).save(img_path)
    fake = MagicMock()
    with patch("escpos.printer.Network", return_value=fake):
        with pytest.raises(Exception, match=r"(chunks|too tall|MAX|height)"):
            await hass.services.async_call(
                DOMAIN,
                "print_image",
                {
                    "image": str(img_path),
                    "fragment_height": 16,
                    "chunk_delay_ms": 0,
                },
                blocking=True,
            )
    assert not fake.image.called
