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
def fake_escpos_module(request: Any) -> Generator[None, None, None]:
    # Do not stub escpos for integration tests; use real network path
    if request.node.get_closest_marker("integration"):
        yield
        return
    escpos = types.ModuleType("escpos")
    printer = types.ModuleType("escpos.printer")

    class _FakeNetwork:
        def __init__(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def set(self, *_: Any, **__: Any) -> None:
            pass

        def text(self, *_: Any, **__: Any) -> None:
            pass

        def qr(self, *_: Any, **__: Any) -> None:
            pass

        def image(self, *_: Any, **__: Any) -> None:
            pass

        def control(self, *_: Any, **__: Any) -> None:
            pass

        def cut(self, *_: Any, **__: Any) -> None:
            pass

        def close(self) -> None:
            pass

        def _set_codepage(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def _raw(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

    class _FakeUsb:
        def __init__(self, id_vendor: int = 0, id_product: int = 0, timeout: int = 0, in_ep: int = 0x82, out_ep: int = 0x01, profile: Any = None, **__: Any):  # type: ignore[no-untyped-def]
            self.idVendor = id_vendor  # Match real USB API
            self.idProduct = id_product  # Match real USB API
            self.timeout = timeout
            self.in_ep = in_ep
            self.out_ep = out_ep
            self.profile = profile

        def set(self, *_: Any, **__: Any) -> None:
            pass

        def text(self, *_: Any, **__: Any) -> None:
            pass

        def qr(self, *_: Any, **__: Any) -> None:
            pass

        def image(self, *_: Any, **__: Any) -> None:
            pass

        def control(self, *_: Any, **__: Any) -> None:
            pass

        def cut(self, *_: Any, **__: Any) -> None:
            pass

        def close(self) -> None:
            pass

        def _set_codepage(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def _raw(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def barcode(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def buzzer(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def beep(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def ln(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def charcode(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

    printer.Network = _FakeNetwork  # type: ignore[attr-defined]
    printer.Usb = _FakeUsb  # type: ignore[attr-defined]
    escpos.printer = printer  # type: ignore[attr-defined]

    sys.modules.setdefault("escpos", escpos)
    sys.modules.setdefault("escpos.printer", printer)
    yield


@pytest.fixture(autouse=True)
def fake_usb_module(request: Any) -> Generator[None, None, None]:
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

    sys.modules.setdefault("usb", usb)
    sys.modules.setdefault("usb.core", usb_core)
    sys.modules.setdefault("usb.util", usb_util)
    yield


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
