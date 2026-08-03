"""Tests for the ``printer.image()`` cached kwarg-support probe.

Mirrors the ``_supported_barcode_kwargs`` coverage in
``test_barcode_force_software.py`` for its ``image()`` analogue in
``image_operations.py``: named-params filtering, the ``**kwargs``
catch-all branch, and the introspection-failure branch.
"""

from __future__ import annotations

from custom_components.escpos_printer.printer.image_operations import (
    _IMAGE_KWARGS_CACHE,
    _supported_image_kwargs,
)


class _NamedParamsPrinter:
    def image(
        self,
        img,
        *,
        high_density_vertical=True,
        high_density_horizontal=True,
        impl="bitImageColumn",
        fragment_height=960,
        center=False,
    ):
        pass


class _VarKwargsPrinter:
    def image(self, img, **kwargs):
        pass


class _VarArgsAndKwargsPrinter:
    def image(self, *args, **kwargs):
        pass


class _UninspectablePrinter:
    # Not a real function -- inspect.signature() raises TypeError on it.
    image = 42


def test_supported_image_kwargs_filters_named_params():
    _IMAGE_KWARGS_CACHE.clear()
    printer = _NamedParamsPrinter()
    supported = _supported_image_kwargs(printer)
    assert supported == frozenset(
        {
            "img",
            "high_density_vertical",
            "high_density_horizontal",
            "impl",
            "fragment_height",
            "center",
        }
    )
    # Second call for the same class hits the cache (returns the same object).
    assert _supported_image_kwargs(printer) is supported


def test_supported_image_kwargs_none_for_var_keyword_catchall():
    _IMAGE_KWARGS_CACHE.clear()
    assert _supported_image_kwargs(_VarKwargsPrinter()) is None


def test_supported_image_kwargs_none_for_args_and_kwargs():
    _IMAGE_KWARGS_CACHE.clear()
    assert _supported_image_kwargs(_VarArgsAndKwargsPrinter()) is None


def test_supported_image_kwargs_none_when_introspection_fails():
    _IMAGE_KWARGS_CACHE.clear()
    assert _supported_image_kwargs(_UninspectablePrinter()) is None
