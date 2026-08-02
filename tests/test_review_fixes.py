"""Regression tests for the full-codebase review fix batch.

Each test pins a specific defect surfaced in the full-codebase review so
it cannot silently regress:

- C3: ``fallback_image`` (and other image source strings) pass through
  ``extract_image_kwargs`` unmodified — no server-side Jinja rendering.
- H1: a keepalive connection is invalidated after a failed operation.
- H3: the decompression-bomb guard is enforced per-decode (no process-global).
- M-ssrf: ``allow_local`` only lifts the port allowlist for private targets.
- M-cancel: cleanup cut severs paper even when the default cut is "none".
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.escpos_printer.const import ATTR_FALLBACK_IMAGE, ATTR_IMAGE
from custom_components.escpos_printer.image_sources import extract_image_kwargs
from custom_components.escpos_printer.printer import (
    NetworkPrinterConfig,
    create_printer_adapter,
)
from custom_components.escpos_printer.printer.mapping_utils import cleanup_cut


def _network_adapter():  # type: ignore[no-untyped-def]
    return create_printer_adapter(NetworkPrinterConfig(host="1.2.3.4", port=9100, timeout=4.0))


# ---------------------------------------------------------------------------
# C3: image source strings (including fallback_image) pass through as-is.
# Server-side Jinja rendering was removed (security fix): the template
# environment reads all HA states with no per-entity permission check, so
# a non-admin caller of the un-admin-gated print_image service could read
# arbitrary sensor state via a crafted `image:` value. Automations still
# work because HA's automation/script engine renders `{{ ... }}` in
# service-call data before dispatch.
# ---------------------------------------------------------------------------


def test_fallback_image_jinja_looking_string_is_passed_through_literally():
    data = {
        ATTR_IMAGE: "camera.front",
        ATTR_FALLBACK_IMAGE: "http://host/{{ 1 + 1 }}.png",
    }
    out = extract_image_kwargs(data, {}, prefix="")
    assert out[ATTR_FALLBACK_IMAGE] == "http://host/{{ 1 + 1 }}.png"


# ---------------------------------------------------------------------------
# H1: a failed keepalive operation must drop the (possibly dead) connection.
# ---------------------------------------------------------------------------


async def test_release_printer_invalidates_keepalive_on_failure(hass):  # type: ignore[no-untyped-def]
    adapter = _network_adapter()
    adapter._keepalive = True
    fake = MagicMock()
    adapter._printer = fake

    await adapter._release_printer(hass, fake, owned=False, failed=True)

    assert adapter._printer is None
    fake.close.assert_called_once()


async def test_release_printer_keeps_keepalive_on_success(hass):  # type: ignore[no-untyped-def]
    adapter = _network_adapter()
    adapter._keepalive = True
    fake = MagicMock()
    adapter._printer = fake

    await adapter._release_printer(hass, fake, owned=False, failed=False)

    assert adapter._printer is fake
    fake.close.assert_not_called()


# ---------------------------------------------------------------------------
# A1: a paper-status probe is a reachability signal PaperStatusSensor
# already fetches every ~30s -- base_adapter.get_paper_status now feeds it
# to status listeners instead of discarding it, split by failure layer:
#   - can't even connect            -> notify offline (unambiguous)
#   - connect ok, DLE EOT ignored   -> notify online, no offline flap
#     (some printers just don't answer this query -- connecting proved
#     reachability already; the original A1 guarantee)
#   - connect ok, query ok          -> notify online
# ---------------------------------------------------------------------------


async def test_paper_status_connect_failure_notifies_offline(hass):  # type: ignore[no-untyped-def]
    adapter = _network_adapter()
    adapter._status = True  # printer was already known online
    received: list[bool] = []
    adapter.add_status_listener(received.append)

    def _boom():
        raise OSError("connection refused")

    adapter._connect = _boom  # type: ignore[method-assign]

    assert await adapter.get_paper_status(hass) is None

    assert adapter.get_status() is False
    assert received == [False]


async def test_paper_status_query_failure_after_connect_does_not_flap_offline(hass):  # type: ignore[no-untyped-def]
    """A printer that ignores/times out on DLE EOT must not flap offline.

    Connecting already proved reachability; the query itself failing
    (common -- not every printer answers paper-status) must not undo that.
    """
    adapter = _network_adapter()
    adapter._status = False  # printer was previously known offline
    received: list[bool] = []
    adapter.add_status_listener(received.append)

    fake = MagicMock()
    fake.paper_status = MagicMock(side_effect=RuntimeError("no response"))
    adapter._connect = lambda: fake  # type: ignore[method-assign]

    assert await adapter.get_paper_status(hass) is None

    assert adapter.get_status() is True
    assert received == [True]
    assert adapter._last_ok is not None


async def test_paper_status_probe_success_marks_online(hass):  # type: ignore[no-untyped-def]
    """A successful paper-status poll is itself a fresh reachability signal."""
    adapter = _network_adapter()
    adapter._status = False  # printer was previously known offline
    received: list[bool] = []
    adapter.add_status_listener(received.append)

    fake = MagicMock()
    fake.paper_status.return_value = 2
    adapter._connect = lambda: fake  # type: ignore[method-assign]

    assert await adapter.get_paper_status(hass) == 2

    assert adapter.get_status() is True
    assert received == [True]
    assert adapter._last_ok is not None


async def test_transport_failure_still_flips_connectivity(hass):  # type: ignore[no-untyped-def]
    adapter = _network_adapter()
    fake = MagicMock()
    fake.barcode = MagicMock(side_effect=OSError("broken pipe"))
    adapter._connect = lambda: fake  # type: ignore[method-assign]

    with pytest.raises(OSError, match="broken pipe"):
        await adapter.print_barcode(hass, code="123456", bc="CODE128")

    assert adapter.get_status() is False
    assert adapter._last_error_reason == "print operation failed"


async def test_connect_failure_through_print_text_flips_connectivity_offline(hass):  # type: ignore[no-untyped-def]
    """A ``_connect()`` failure must reach the offline notification too.

    Regression: every operation acquired its printer *before* entering
    the try/finally that calls ``_release_printer`` on failure, so a
    connect-time exception propagated straight out without ever
    notifying listeners -- the connectivity sensor stayed latched
    "Online" through repeated connect failures.
    """
    adapter = _network_adapter()
    adapter._status = True  # printer was already known online
    received: list[bool] = []
    adapter.add_status_listener(received.append)

    def _boom():
        raise OSError("connection refused")

    adapter._connect = _boom  # type: ignore[method-assign]

    with pytest.raises(OSError, match="connection refused"):
        await adapter.print_text(hass, text="hello")

    assert adapter.get_status() is False
    assert received == [False]


async def test_connect_failure_through_feed_flips_connectivity_offline(hass):  # type: ignore[no-untyped-def]
    adapter = _network_adapter()
    adapter._status = True
    received: list[bool] = []
    adapter.add_status_listener(received.append)

    def _boom():
        raise OSError("connection refused")

    adapter._connect = _boom  # type: ignore[method-assign]

    with pytest.raises(OSError, match="connection refused"):
        await adapter.feed(hass, lines=1)

    assert adapter.get_status() is False
    assert received == [False]


async def test_barcode_validation_error_does_not_flip_connectivity(hass):  # type: ignore[no-untyped-def]
    from escpos.exceptions import BarcodeTypeError

    adapter = _network_adapter()
    adapter._status = True
    fake = MagicMock()
    fake.barcode = MagicMock(side_effect=BarcodeTypeError("bad barcode type"))
    adapter._connect = lambda: fake  # type: ignore[method-assign]

    with pytest.raises(BarcodeTypeError):
        await adapter.print_barcode(hass, code="123456", bc="CODE128")

    assert adapter.get_status() is True  # unchanged -- not a transport failure


# ---------------------------------------------------------------------------
# H3: decompression-bomb guard is per-decode (does not touch PIL's global).
# ---------------------------------------------------------------------------


def test_image_processor_rejects_oversized_image():
    import io

    from PIL import Image
    import PIL.Image

    from custom_components.escpos_printer.printer.image_processor import (
        ImageProcessOptions,
        process_image_from_bytes,
    )

    original_global = PIL.Image.MAX_IMAGE_PIXELS
    # 5000x5000 = 25M px: above our 20M cap but below Pillow's ~89M default,
    # so our explicit per-decode guard — not Pillow's global — must reject
    # it. A solid image compresses to a few KB so the fixture is cheap.
    buf = io.BytesIO()
    Image.new("L", (5000, 5000), color=255).save(buf, format="PNG")
    with pytest.raises(ValueError, match="exceeds the maximum"):
        process_image_from_bytes(buf.getvalue(), ImageProcessOptions(width=100))
    # The integration must not have mutated Pillow's process-global limit.
    assert original_global == PIL.Image.MAX_IMAGE_PIXELS


# ---------------------------------------------------------------------------
# M-ssrf: allow_local only lifts the port allowlist for private targets.
# ---------------------------------------------------------------------------


async def test_allow_local_rejects_public_nonstandard_port(hass):  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer import security

    with patch.object(security, "_resolve_hostname_sync", return_value=["93.184.216.34"]):
        with pytest.raises(HomeAssistantError, match="private/LAN"):
            await security.validate_image_url_and_resolve(
                hass, "http://example.com:8080/x.png", allow_local=True
            )


async def test_allow_local_permits_private_nonstandard_port(hass):  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer import security

    with patch.object(security, "_resolve_hostname_sync", return_value=["192.168.1.50"]):
        _url, addrs = await security.validate_image_url_and_resolve(
            hass, "http://printer.local:8080/x.png", allow_local=True
        )
    assert addrs == ["192.168.1.50"]


# ---------------------------------------------------------------------------
# M-cancel: cleanup cut severs paper even when the default cut is "none".
# ---------------------------------------------------------------------------


def test_cleanup_cut_forces_full_for_none():
    assert cleanup_cut("none") == "full"
    assert cleanup_cut(None) == "full"
    assert cleanup_cut("") == "full"


def test_cleanup_cut_honours_explicit_mode():
    assert cleanup_cut("partial") == "partial"
    assert cleanup_cut("full") == "full"


# ---------------------------------------------------------------------------
# C2: an options change reloads the entry so it takes effect immediately.
# The options flow extends OptionsFlowWithReload, which HA guarantees to
# reload the entry on a (changed) options save.
# ---------------------------------------------------------------------------


def test_options_flow_uses_reload_base():
    from homeassistant import config_entries

    from custom_components.escpos_printer._config_flow.options_flow import (
        EscposOptionsFlowHandler,
    )

    assert issubclass(EscposOptionsFlowHandler, config_entries.OptionsFlowWithReload)


# ---------------------------------------------------------------------------
# H6: a printer that's unreachable at setup raises ConfigEntryNotReady
# (retry-with-backoff) instead of hard-failing the entry.
# ---------------------------------------------------------------------------


async def test_setup_entry_raises_config_entry_not_ready(hass):  # type: ignore[no-untyped-def]
    from homeassistant.const import CONF_HOST, CONF_PORT
    from homeassistant.exceptions import ConfigEntryNotReady
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.escpos_printer import async_setup_entry
    from custom_components.escpos_printer.const import CONF_KEEPALIVE, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        # keepalive forces an eager connect at start() — the only blocking
        # work that can fail and should trigger ConfigEntryNotReady.
        options={CONF_KEEPALIVE: True},
    )
    entry.add_to_hass(hass)

    with patch("escpos.printer.Network", side_effect=OSError("connection refused")):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)


# ---------------------------------------------------------------------------
# H9: a multi-target call attempts every printer and aggregates failures.
# ---------------------------------------------------------------------------


async def test_for_each_target_aggregates_partial_failure(hass):  # type: ignore[no-untyped-def]
    from custom_components.escpos_printer.services import _handler_utils as hu

    e1 = MagicMock(entry_id="e1", title="Printer A")
    e2 = MagicMock(entry_id="e2", title="Printer B")
    call = MagicMock()
    call.hass = hass

    attempted: list[str] = []

    async def _body(entry, _adapter, _defaults, _config):  # type: ignore[no-untyped-def]
        attempted.append(entry.entry_id)
        if entry.entry_id == "e1":
            raise HomeAssistantError("printer offline")

    with (
        patch.object(hu, "_async_get_target_entries", AsyncMock(return_value=[e1, e2])),
        patch.object(hu, "_get_adapter_and_defaults", return_value=(MagicMock(), {}, MagicMock())),
    ):
        with pytest.raises(HomeAssistantError, match="Printer A"):
            await hu._for_each_target(call, "print_text", _body)

    # The second target is still attempted even though the first failed.
    assert attempted == ["e1", "e2"]


async def test_for_each_target_single_target_propagates_exact_error(hass):  # type: ignore[no-untyped-def]
    from homeassistant.exceptions import ServiceValidationError

    from custom_components.escpos_printer.services import _handler_utils as hu

    e1 = MagicMock(entry_id="e1", title="Printer A")
    call = MagicMock()
    call.hass = hass

    async def _body(_entry, _adapter, _defaults, _config):  # type: ignore[no-untyped-def]
        raise ServiceValidationError("bad value")

    with (
        patch.object(hu, "_async_get_target_entries", AsyncMock(return_value=[e1])),
        patch.object(hu, "_get_adapter_and_defaults", return_value=(MagicMock(), {}, MagicMock())),
    ):
        # Single-target: the original ServiceValidationError (with its
        # translation/status context) must propagate untouched.
        with pytest.raises(ServiceValidationError):
            await hu._for_each_target(call, "print_text", _body)


async def test_for_each_target_reraises_unauthorized_in_multi(hass):  # type: ignore[no-untyped-def]
    """A permission denial on a broadcast must propagate as Unauthorized.

    (Review S-M3: the aggregate `except Exception` must not downgrade an
    auth failure into a generic "N of M failed" string.)
    """
    from homeassistant.exceptions import Unauthorized

    from custom_components.escpos_printer.services import _handler_utils as hu

    e1 = MagicMock(entry_id="e1", title="Printer A")
    e2 = MagicMock(entry_id="e2", title="Printer B")
    call = MagicMock()
    call.hass = hass

    async def _body(entry, _adapter, _defaults, _config):  # type: ignore[no-untyped-def]
        if entry.entry_id == "e1":
            raise Unauthorized

    with (
        patch.object(hu, "_async_get_target_entries", AsyncMock(return_value=[e1, e2])),
        patch.object(hu, "_get_adapter_and_defaults", return_value=(MagicMock(), {}, MagicMock())),
    ):
        with pytest.raises(Unauthorized):
            await hu._for_each_target(call, "print_image", _body)


# ---------------------------------------------------------------------------
# auto_resize: the per-decode cap is raised (but still bounded) when the
# caller opts into downscaling. (Review: bomb-guard regression.)
# ---------------------------------------------------------------------------


def test_auto_resize_permits_above_base_cap():
    import io

    from PIL import Image

    from custom_components.escpos_printer.printer.image_processor import (
        ImageProcessOptions,
        process_image_from_bytes,
    )

    buf = io.BytesIO()
    Image.new("L", (5000, 5000), color=255).save(buf, format="PNG")  # 25M px
    # 25M > the 20M base cap, but auto_resize raises the ceiling to 40M and
    # downscales — so it must succeed, not raise.
    out = process_image_from_bytes(buf.getvalue(), ImageProcessOptions(width=384, auto_resize=True))
    assert out.width <= 384


def test_auto_resize_still_bounded():
    import io

    from PIL import Image

    from custom_components.escpos_printer.printer.image_processor import (
        ImageProcessOptions,
        process_image_from_bytes,
    )

    buf = io.BytesIO()
    Image.new("L", (7000, 7000), color=255).save(buf, format="PNG")  # 49M px
    # Even with auto_resize the ceiling (40M) is enforced before load().
    with pytest.raises(ValueError, match="exceeds the maximum"):
        process_image_from_bytes(buf.getvalue(), ImageProcessOptions(width=384, auto_resize=True))
