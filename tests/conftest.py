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
    # Do not stub escpos for integration tests; use real CUPS path
    if request.node.get_closest_marker("integration"):
        yield
        return
    escpos = types.ModuleType("escpos")
    printer = types.ModuleType("escpos.printer")

    class _FakeDummyPrinter:
        """Fake Dummy printer that collects ESC/POS commands."""

        def __init__(self, *_, **__):  # type: ignore[no-untyped-def]
            self._buffer = b""

        @property
        def output(self) -> bytes:
            """Return accumulated ESC/POS data."""
            return self._buffer

        def set(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1b@"  # ESC @ (initialize)

        def text(self, text: str = "", *_: Any, **__: Any) -> None:
            self._buffer += text.encode("utf-8", errors="replace")

        def qr(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1dQR"  # Fake QR command

        def image(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1dIMG"  # Fake image command

        def control(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\n"

        def cut(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1dV"  # ESC/POS cut

        def ln(self, lines: int = 1) -> None:
            self._buffer += b"\n" * lines

        def barcode(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1dBC"  # Fake barcode

        def buzzer(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1bBZ"  # Fake buzzer

        def beep(self, *_: Any, **__: Any) -> None:
            self._buffer += b"\x1bBZ"  # Fake buzzer

        def charcode(self, *_: Any, **__: Any) -> None:
            pass

        def close(self) -> None:
            pass

        def _set_codepage(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def _raw(self, data: bytes = b"", *_, **__):  # type: ignore[no-untyped-def]
            self._buffer += data

    # Keep CupsPrinter for backwards compatibility in tests
    printer.CupsPrinter = _FakeDummyPrinter  # type: ignore[attr-defined]
    printer.Dummy = _FakeDummyPrinter  # type: ignore[attr-defined]
    escpos.printer = printer  # type: ignore[attr-defined]

    sys.modules.setdefault("escpos", escpos)
    sys.modules.setdefault("escpos.printer", printer)
    yield


@pytest.fixture(autouse=True)
def fake_cups_module(request: Any) -> Generator[None, None, None]:
    """Provide a fake cups module for unit tests."""
    if request.node.get_closest_marker("integration"):
        yield
        return

    cups = types.ModuleType("cups")

    class _FakeConnection:
        _job_counter = 0

        def __init__(self, *_, **__):  # type: ignore[no-untyped-def]
            pass

        def getPrinters(self) -> dict[str, dict[str, Any]]:
            return {
                "TestPrinter": {
                    "printer-state": 3,  # idle
                    "printer-state-reasons": ["none"],
                }
            }

        def printFile(self, printer: str, filename: str, title: str, options: dict[str, str]) -> int:
            """Fake printFile that returns a job ID."""
            _FakeConnection._job_counter += 1
            return _FakeConnection._job_counter

    def _setServer(server: str) -> None:
        """Fake setServer function."""
        pass

    cups.Connection = _FakeConnection  # type: ignore[attr-defined]
    cups.setServer = _setServer  # type: ignore[attr-defined]
    sys.modules.setdefault("cups", cups)
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
