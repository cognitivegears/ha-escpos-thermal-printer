from __future__ import annotations

from typing import Any

import pytest

from custom_components.escpos_printer.printer import EscposPrinterAdapter, PrinterConfig


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
    def barcode(self, code: str, bc: str, **kwargs: Any) -> None:
        if "force_software" in kwargs:
            # Simulate older python-escpos rejecting the kwarg
            raise TypeError("unexpected keyword argument 'force_software'")
        self.calls.append((code, bc, kwargs))


@pytest.mark.asyncio
async def test_barcode_passes_force_software(monkeypatch: Any) -> None:
    created: list[FakePrinterAcceptFS] = []

    def fake_cups() -> Any:
        def _factory(*args: Any, **kwargs: Any) -> FakePrinterAcceptFS:
            inst = FakePrinterAcceptFS()
            created.append(inst)
            return inst
        return _factory

    from custom_components.escpos_printer import printer as printer_mod

    monkeypatch.setattr(printer_mod, "_get_cups_printer", fake_cups)

    adapter = EscposPrinterAdapter(PrinterConfig(printer_name="TestPrinter"))
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
async def test_barcode_retries_without_force_software(monkeypatch: Any) -> None:
    created: list[FakePrinterRejectFS] = []

    def fake_cups() -> Any:
        def _factory(*args: Any, **kwargs: Any) -> FakePrinterRejectFS:
            inst = FakePrinterRejectFS()
            created.append(inst)
            return inst
        return _factory

    from custom_components.escpos_printer import printer as printer_mod

    monkeypatch.setattr(printer_mod, "_get_cups_printer", fake_cups)

    adapter = EscposPrinterAdapter(PrinterConfig(printer_name="TestPrinter"))
    hass = HassStub()

    await adapter.print_barcode(
        hass,
        code="123456",
        bc="CODE128",
        force_software="graphics",
    )

    # Verify that after TypeError, a successful call without force_software occurred
    assert created, "No printer instances were created"
    target = None
    for inst in created:
        if inst.calls:
            target = inst
            break
    assert target is not None, "No barcode() calls recorded on any instance"
    _code, _bc, kwargs = target.calls[-1]
    assert "force_software" not in kwargs
