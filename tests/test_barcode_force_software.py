from __future__ import annotations

from typing import Any

import pytest

from custom_components.escpos_printer.printer import NetworkPrinterAdapter, NetworkPrinterConfig


class HassStub:
    async def async_add_executor_job(self, func: Any, *args: Any, **kwargs: Any) -> Any:
        # Execute synchronously in tests
        return func(*args, **kwargs)


class FakePrinterAcceptFS:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []

    def set(self, **kwargs: Any) -> None:
        pass

    def barcode(self, code: str, bc: str, **kwargs: Any) -> None:
        self.calls.append((code, bc, kwargs))

    def close(self) -> None:
        pass


class FakePrinterRejectFS(FakePrinterAcceptFS):
    """Simulates an older python-escpos with no ``force_software`` parameter.

    Explicit named parameters (no ``**kwargs`` catch-all) mirror the real
    ``Escpos.barcode`` signature shape, so
    ``barcode_operations._supported_barcode_kwargs`` — which decides support
    via ``inspect.signature`` up front rather than retrying after a
    ``TypeError`` — correctly identifies ``force_software`` as unsupported
    and omits it before ever calling ``barcode()``.
    """

    def barcode(
        self,
        code: str,
        bc: str,
        *,
        height: int = 64,
        width: int = 3,
        pos: str = "BELOW",
        font: str = "A",
        align_ct: bool = True,
        check: bool = True,
    ) -> None:
        self.calls.append(
            (
                code,
                bc,
                {
                    "height": height,
                    "width": width,
                    "pos": pos,
                    "font": font,
                    "align_ct": align_ct,
                    "check": check,
                },
            )
        )


@pytest.mark.asyncio
async def test_barcode_passes_force_software(monkeypatch: Any) -> None:
    created: list[FakePrinterAcceptFS] = []

    def fake_network() -> Any:
        def _factory(*args: Any, **kwargs: Any) -> FakePrinterAcceptFS:
            inst = FakePrinterAcceptFS()
            created.append(inst)
            return inst

        return _factory

    from custom_components.escpos_printer.printer import network_adapter as printer_mod

    monkeypatch.setattr(printer_mod, "_get_network_printer", fake_network)

    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="127.0.0.1", port=9100))
    hass = HassStub()

    await adapter.print_barcode(
        hass,
        code="123456",
        bc="CODE128",
        force_software=True,
    )

    # Verify force_software was passed to barcode() on the instance used for printing
    assert created, "No printer instances were created"
    target = None
    for inst in created:
        if inst.calls:
            target = inst
            break
    assert target is not None, "No barcode() calls recorded on any instance"
    _code, _bc, kwargs = target.calls[-1]
    assert kwargs.get("force_software") is True


@pytest.mark.asyncio
async def test_barcode_omits_unsupported_force_software(monkeypatch: Any) -> None:
    created: list[FakePrinterRejectFS] = []

    def fake_network() -> Any:
        def _factory(*args: Any, **kwargs: Any) -> FakePrinterRejectFS:
            inst = FakePrinterRejectFS()
            created.append(inst)
            return inst

        return _factory

    from custom_components.escpos_printer.printer import network_adapter as printer_mod

    monkeypatch.setattr(printer_mod, "_get_network_printer", fake_network)

    adapter = NetworkPrinterAdapter(NetworkPrinterConfig(host="127.0.0.1", port=9100))
    hass = HassStub()

    await adapter.print_barcode(
        hass,
        code="123456",
        bc="CODE128",
        force_software="graphics",
    )

    # Verify force_software was omitted up front (no TypeError/retry involved)
    assert created, "No printer instances were created"
    target = None
    for inst in created:
        if inst.calls:
            target = inst
            break
    assert target is not None, "No barcode() calls recorded on any instance"
    _code, _bc, kwargs = target.calls[-1]
    assert "force_software" not in kwargs
