from collections.abc import AsyncIterator, Generator
import io
from pathlib import Path
import struct
import sys
import threading
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: Any) -> None:
    return


@pytest.fixture(autouse=True)
def fake_escpos_module(
    request: Any, monkeypatch: pytest.MonkeyPatch
) -> Generator[None]:
    # Do not stub escpos for integration tests; use real network path
    if request.node.get_closest_marker("integration"):
        yield
        return
    escpos = types.ModuleType("escpos")
    printer = types.ModuleType("escpos.printer")
    escpos_pkg = types.ModuleType("escpos.escpos")

    # Single no-op surface shared by every fake. Adding a method here is one
    # change instead of three — and no risk of one fake silently lacking a
    # method that another exposes.
    class _FakeEscposCommon:
        def set(self, *_: Any, **__: Any) -> None: pass
        def text(self, *_: Any, **__: Any) -> None: pass
        def qr(self, *_: Any, **__: Any) -> None: pass
        def image(self, *_: Any, **__: Any) -> None: pass
        def control(self, *_: Any, **__: Any) -> None: pass
        def cut(self, *_: Any, **__: Any) -> None: pass
        def close(self) -> None: pass
        def _set_codepage(self, *_: Any, **__: Any) -> None: pass
        def _raw(self, *_: Any, **__: Any) -> None: pass
        def barcode(self, *_: Any, **__: Any) -> None: pass
        def buzzer(self, *_: Any, **__: Any) -> None: pass
        def beep(self, *_: Any, **__: Any) -> None: pass
        def ln(self, *_: Any, **__: Any) -> None: pass
        def charcode(self, *_: Any, **__: Any) -> None: pass

    class _FakeNetwork(_FakeEscposCommon):
        def __init__(self, *_: Any, **__: Any) -> None: pass

    class _FakeUsb(_FakeEscposCommon):
        def __init__(
            self, id_vendor: int = 0, id_product: int = 0, timeout: int = 0,
            in_ep: int = 0x82, out_ep: int = 0x01, profile: Any = None, **__: Any,
        ) -> None:
            self.idVendor = id_vendor  # Match real USB API
            self.idProduct = id_product  # Match real USB API
            self.timeout = timeout
            self.in_ep = in_ep
            self.out_ep = out_ep
            self.profile = profile

    class _FakeEscposBase(_FakeEscposCommon):
        def __init__(self, profile: Any = None, **__: Any) -> None:
            self.profile = profile

    printer.Network = _FakeNetwork  # type: ignore[attr-defined]
    printer.Usb = _FakeUsb  # type: ignore[attr-defined]
    escpos.printer = printer  # type: ignore[attr-defined]
    escpos_pkg.Escpos = _FakeEscposBase  # type: ignore[attr-defined]
    escpos.escpos = escpos_pkg  # type: ignore[attr-defined]

    # Use monkeypatch.setitem so each test's stub is automatically reverted at
    # teardown. Previously this used sys.modules.setdefault which never cleaned
    # up — that leaked the fakes into integration tests run in the same session
    # and forced an _ensure_real_escpos hack on the integration-test side.
    monkeypatch.setitem(sys.modules, "escpos", escpos)
    monkeypatch.setitem(sys.modules, "escpos.printer", printer)
    monkeypatch.setitem(sys.modules, "escpos.escpos", escpos_pkg)

    # The Bluetooth subclass is cached at module scope; invalidate it so the
    # next make_bluetooth_escpos call resolves the (just-installed) fake base.
    # Drop again on teardown so a later integration test resolves the real
    # Escpos module.
    from custom_components.escpos_printer.printer import _escpos_bluetooth

    _escpos_bluetooth._get_bluetooth_escpos_cls.cache_clear()
    try:
        yield
    finally:
        _escpos_bluetooth._get_bluetooth_escpos_cls.cache_clear()


@pytest.fixture(autouse=True)
def fake_usb_module(
    request: Any, monkeypatch: pytest.MonkeyPatch
) -> Generator[None]:
    """Provide a fake usb module for unit tests."""
    if request.node.get_closest_marker("integration"):
        yield
        return

    usb = types.ModuleType("usb")
    usb_core = types.ModuleType("usb.core")
    usb_util = types.ModuleType("usb.util")

    def _fake_find(id_vendor: int | None = None, id_product: int | None = None, find_all: bool = False, **kwargs: Any) -> Any:
        if find_all:
            return []  # Return empty list for unit tests
        return None

    def _fake_get_string(device: Any, index: int) -> str | None:
        if index == 1:
            return "Fake Manufacturer"
        if index == 2:
            return "Fake Product"
        return None

    usb_core.find = _fake_find  # type: ignore[attr-defined]
    usb_util.get_string = _fake_get_string  # type: ignore[attr-defined]
    usb.core = usb_core  # type: ignore[attr-defined]
    usb.util = usb_util  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "usb", usb)
    monkeypatch.setitem(sys.modules, "usb.core", usb_core)
    monkeypatch.setitem(sys.modules, "usb.util", usb_util)
    yield


@pytest.fixture(autouse=True)
def fake_bluetooth_module(request: Any) -> Generator[None]:
    """Stub out dbus-fast and AF_BLUETOOTH for unit tests.

    Unit tests must not touch a real D-Bus or kernel Bluetooth stack. The
    bluetooth helpers gracefully degrade when ``dbus_fast`` import fails
    or D-Bus isn't reachable, so by default we just remove dbus_fast from
    sys.modules and let the helpers return an empty paired list. Tests
    that need to drive specific D-Bus replies can install their own fake
    via ``sys.modules["dbus_fast"]``.
    """
    if request.node.get_closest_marker("integration"):
        yield
        return

    # Patch the RFCOMM transport seam so we never touch a real socket.
    # Tests that want to assert on behavior can monkeypatch this further.
    from custom_components.escpos_printer.printer import bluetooth_transport as bt_mod

    class _StubTransport:
        def __init__(self) -> None:
            self.written: list[bytes] = []
            self.closed = False

        def write(self, data: bytes) -> None:
            self.written.append(data)

        def close(self) -> None:
            self.closed = True

    def _stub_open(_mac: str, _channel: int, _timeout: float) -> _StubTransport:
        return _StubTransport()

    original = bt_mod.open_rfcomm_transport
    bt_mod.open_rfcomm_transport = _stub_open  # type: ignore[assignment]
    try:
        yield
    finally:
        bt_mod.open_rfcomm_transport = original  # type: ignore[assignment]


@pytest.fixture(autouse=True)
def disable_platform_forwarding_for_unit_tests(monkeypatch: Any, request: Any) -> None:
    """Avoid starting HA http/notify stack in unit tests.

    For tests not marked as 'integration', prevent platform forwarding by
    setting PLATFORMS to an empty list. Service registration remains intact.
    """
    if request.node.get_closest_marker("integration"):
        return
    try:
        import custom_components.escpos_printer.__init__ as cc_init

        # Allow notify platform during unit tests; disable others via env flag
        monkeypatch.setattr(cc_init, "PLATFORMS", ["notify"], raising=False)
        monkeypatch.setenv("ESC_POS_DISABLE_PLATFORMS", "0")
    except Exception:
        pass


@pytest.fixture(autouse=True)
def stub_http_component_for_unit_tests(monkeypatch: Any, request: Any) -> None:
    """Provide a minimal stub for the Home Assistant http component in unit tests.

    The real http component can spawn background threads; stubbing avoids lingering
    thread assertions in unit tests. Integration tests use the real component.
    """
    if request.node.get_closest_marker("integration"):
        return
    mod = types.ModuleType("homeassistant.components.http")
    async def _ok(*args: Any, **kwargs: Any) -> bool:
        return True
    # Provide the setup entrypoints expected by HA
    mod.async_setup = _ok  # type: ignore[attr-defined]
    mod.async_setup_entry = _ok  # type: ignore[attr-defined]
    mod.async_unload_entry = _ok  # type: ignore[attr-defined]
    sys.modules.setdefault("homeassistant.components.http", mod)


@pytest.fixture(autouse=True)
def allow_all_paths_for_unit_tests(monkeypatch: Any, request: Any) -> None:
    """Permit `tmp_path`-based image fixtures in unit tests.

    Real HA enforces `allowlist_external_dirs` for every local-file
    image source. Unit tests write into `tmp_path` (outside `/config`),
    so without this monkeypatch every image test would fail with
    "Path outside Home Assistant allowlist_external_dirs". Integration
    tests keep the real behavior.
    """
    if request.node.get_closest_marker("integration"):
        return
    try:
        # Patch the class method so any `hass.config.is_allowed_path`
        # call during the test returns True. Tests that need to
        # exercise allowlist rejection monkeypatch this back to False
        # on their own `hass.config` instance.
        monkeypatch.setattr(
            "homeassistant.core_config.Config.is_allowed_path",
            lambda _self, _path: True,
        )
    except Exception:
        pass


@pytest.fixture(autouse=True)
def avoid_safe_shutdown_thread(monkeypatch: Any, request: Any) -> None:
    """Prevent Home Assistant's safe-shutdown background thread in unit tests.

    Intercepts thread starts whose target function is named '_run_safe_shutdown_loop'
    and short-circuits them. This avoids lingering thread assertions from the
    test harness. Integration tests keep the real behavior.
    """
    if request.node.get_closest_marker("integration"):
        return

    _orig_start = threading.Thread.start

    def _patched_start(self: Any, *args: Any, **kwargs: Any) -> Any:
        target_name = getattr(getattr(self, "_target", None), "__name__", None)
        if target_name == "_run_safe_shutdown_loop":
            # Do not start this thread in unit tests
            return None
        return _orig_start(self, *args, **kwargs)

    monkeypatch.setattr(threading.Thread, "start", _patched_start, raising=True)


# ---------------------------------------------------------------------------
# Shared fixtures for image-pipeline regression tests.
#
# Added in support of Phase 3 T-C1..T-C4 / T-H1..T-H7 from
# `.full-review/05-final-report.md`. Promoting these to conftest.py
# eliminates the `_setup_entry` duplication across the image test files
# and gives every new regression test a clean primitive to build on.
# ---------------------------------------------------------------------------


@pytest.fixture
async def network_entry(hass: Any) -> Any:
    """Set up a Network printer config entry. Replaces per-test `_setup_entry`."""
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.escpos_printer.const import (
        CONF_HOST,
        CONF_PORT,
        DOMAIN,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="1.2.3.4:9100",
        data={CONF_HOST: "1.2.3.4", CONF_PORT: 9100},
        unique_id="1.2.3.4:9100",
        version=3,
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
def make_symlink(tmp_path: Path):  # type: ignore[no-untyped-def]
    """Return a helper that creates a ``.png`` symlink to an arbitrary target.

    Used by `test_image_sources.py` to verify the symlink-traversal hole
    (Phase 2 S-C2) is closed: a symlink under an allowlisted directory
    that points outside it must be rejected.
    """

    def _make(target: Path, *, link_name: str = "logo.png") -> Path:
        link = tmp_path / link_name
        link.symlink_to(target)
        return link

    return _make


@pytest.fixture
def restricted_user_context():  # type: ignore[no-untyped-def]
    """Build a ``Context`` whose user is denied per-entity reads.

    Returns a callable ``(hass, denied_entity_ids) -> Context``. The
    user is created via HA's auth manager, marked non-admin, and given
    a policy that denies the named entities. Used to verify the
    camera/image authorization check (Phase 2 S-H1 / Phase 3 T-C3).
    """

    async def _build(hass: Any, denied_entity_ids: list[str]) -> Any:
        from homeassistant.auth.permissions import PolicyPermissions
        from homeassistant.core import Context

        user = await hass.auth.async_create_user("restricted")
        # Build an entities policy that denies the named entity_ids.
        policy = {
            "entities": {
                "entity_ids": dict.fromkeys(denied_entity_ids, False)
            }
        }
        user.permissions = PolicyPermissions(policy, None)
        user.is_admin = False
        return Context(user_id=user.id)

    return _build


def _slow_aiter(
    chunks: list[bytes], delay_s: float
):
    async def _iter() -> AsyncIterator[bytes]:
        import asyncio

        for chunk in chunks:
            await asyncio.sleep(delay_s)
            yield chunk

    return _iter()


@pytest.fixture
def slow_aiter():  # type: ignore[no-untyped-def]
    """Return a factory ``(chunks, delay_s) -> async iterator``.

    Used by the slow-loris HTTP test to simulate a server that
    dribbles bytes one chunk at a time (Phase 2 S-M4 / Phase 3 T-H5).
    """
    return _slow_aiter


@pytest.fixture
def decompression_bomb_png():  # type: ignore[no-untyped-def]
    """Return a callable that builds a tiny PNG with attacker-set dimensions.

    The IHDR chunk is patched to declare huge ``width x height`` so
    Pillow's bomb protection should refuse to decode it. Used by Phase
    3 T-C4 (decompression bomb regression).
    """

    def _build(width: int, height: int) -> bytes:
        # Generate a real 1x1 PNG then rewrite the IHDR width/height.
        from PIL import Image as _Image

        buf = io.BytesIO()
        _Image.new("L", (1, 1), color=128).save(buf, format="PNG")
        raw = bytearray(buf.getvalue())
        # PNG layout: 8-byte signature, then IHDR chunk
        # length(4) + type(4)='IHDR' + data(13) + crc(4). Width is the
        # first 4 bytes of data; height the next 4. We overwrite both;
        # the CRC will no longer match, but Pillow validates dimensions
        # against MAX_IMAGE_PIXELS *before* CRC, so the bomb error fires
        # first.
        ihdr_data_start = 8 + 4 + 4
        struct.pack_into(">II", raw, ihdr_data_start, width, height)
        return bytes(raw)

    return _build


def _fake_aiohttp_response(
    status: int = 200,
    headers: dict[str, str] | None = None,
    body: bytes = b"",
    chunks: list[bytes] | None = None,
) -> MagicMock:
    """Build a minimal ``aiohttp.ClientResponse``-shaped mock."""
    resp = MagicMock()
    resp.status = status
    resp.headers = headers or {"Content-Type": "image/png"}
    resp.raise_for_status = MagicMock()

    async def _iter_chunked(_size: int):
        for chunk in chunks if chunks is not None else [body]:
            yield chunk

    resp.content.iter_chunked = _iter_chunked
    resp.read = AsyncMock(return_value=body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=None)
    return resp


@pytest.fixture
def mock_pooled_aiohttp(monkeypatch: pytest.MonkeyPatch):  # type: ignore[no-untyped-def]
    """Return a helper that installs a fake ``async_get_clientsession``.

    The fake session's ``.get(url)`` returns whatever the test passes in.
    Used by SSRF / fallback-bug / slow-loris regression tests so we
    don't need a real HTTP server (Phase 3 T-C1, T-H5, T-M3).
    """

    def _install(response_factory):  # type: ignore[no-untyped-def]
        session = MagicMock()

        def _get(_url: str, **_kwargs: Any) -> MagicMock:
            return response_factory()

        session.get = _get
        from homeassistant.helpers import aiohttp_client

        monkeypatch.setattr(
            aiohttp_client, "async_get_clientsession", lambda _hass: session
        )
        return session

    return _install


# Expose `_fake_aiohttp_response` to tests via the conftest namespace.
fake_aiohttp_response = _fake_aiohttp_response
