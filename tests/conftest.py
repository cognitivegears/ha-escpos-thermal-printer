from collections.abc import Generator
import sys
import threading
import types
from typing import Any

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
