"""Regression tests: the profile kwarg must survive python-escpos's round-trip.

0.7.3 passed the *resolved profile object* into the printer constructors.
``Escpos.__init__`` re-runs that kwarg through
``escpos.capabilities.get_profile()``, whose isinstance fast-path only
accepts instances of the library's *default* profile class — a specific
profile instance (``TMT20IIProfile``, …) fell through to a dict lookup
keyed by the object itself, so every connect raised
``KeyError: <…TMT20IIProfile object…>`` and all printing broke for any
entry with a configured profile.

The conftest escpos fakes now mirror that round-trip (their ``__init__``
calls the real ``get_profile()``), so these connects exercise the same
contract the real library enforces, without any I/O.
"""

from custom_components.escpos_printer.printer.bluetooth_adapter import (
    BluetoothPrinterAdapter,
)
from custom_components.escpos_printer.printer.config import (
    BluetoothPrinterConfig,
    NetworkPrinterConfig,
    UsbPrinterConfig,
)
from custom_components.escpos_printer.printer.network_adapter import (
    NetworkPrinterAdapter,
)
from custom_components.escpos_printer.printer.usb_adapter import UsbPrinterAdapter


def _network_config(profile: str) -> NetworkPrinterConfig:
    return NetworkPrinterConfig(
        host="192.0.2.1", port=9100, timeout=1.0, codepage="", profile=profile, line_width=48
    )


def test_network_connect_profile_roundtrips() -> None:
    adapter = NetworkPrinterAdapter(_network_config("TM-T20II"))
    printer = adapter._connect()
    assert type(printer.profile).__name__ == "TMT20IIProfile"
    assert printer.profile.profile_data["media"]["width"]["pixels"] == 576


def test_usb_connect_profile_roundtrips() -> None:
    adapter = UsbPrinterAdapter(
        UsbPrinterConfig(
            vendor_id=0x04B8,
            product_id=0x0E28,
            in_ep=0x82,
            out_ep=0x01,
            timeout=1.0,
            codepage="",
            profile="TM-T20II",
            line_width=48,
        )
    )
    printer = adapter._connect()
    assert type(printer.profile).__name__ == "TMT20IIProfile"


def test_bluetooth_connect_profile_roundtrips() -> None:
    adapter = BluetoothPrinterAdapter(
        BluetoothPrinterConfig(
            mac="AA:BB:CC:DD:EE:FF",
            rfcomm_channel=1,
            timeout=1.0,
            codepage="",
            profile="TM-T20II",
            line_width=48,
        )
    )
    printer = adapter._connect()
    assert type(printer.profile).__name__ == "TMT20IIProfile"


def test_profile_for_constructor_returns_name() -> None:
    adapter = NetworkPrinterAdapter(_network_config("TM-T20II"))
    assert adapter._profile_for_constructor() == "TM-T20II"


def test_profile_for_constructor_unknown_degrades_to_none() -> None:
    """Unknown profile keeps the old degrade-to-library-default behaviour."""
    adapter = NetworkPrinterAdapter(_network_config("definitely_not_a_real_profile"))
    assert adapter._profile_for_constructor() is None
    # And the connect itself must not raise — it falls back to the default.
    printer = adapter._connect()
    assert printer.profile is not None


def test_profile_for_constructor_empty_is_none() -> None:
    adapter = NetworkPrinterAdapter(_network_config(""))
    assert adapter._profile_for_constructor() is None
