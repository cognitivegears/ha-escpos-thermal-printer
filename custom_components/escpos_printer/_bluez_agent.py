# ruff: noqa: F821, UP037, N802
# mypy: disable-error-code="no-untyped-def,name-defined"
#
# This module deliberately has no ``from __future__ import annotations``:
# dbus-fast reads each D-Bus signature ("o", "s", "u", ...) from the method
# annotations, and postponed evaluation would wrap them in a second pair of
# quotes. Bluez also dictates the CamelCase method names of ``Agent1``.
"""The throw-away ``org.bluez.Agent1`` that answers pairing requests."""

from typing import Any

# Legacy PIN used when the user didn't supply one; printers almost always ship with it.
DEFAULT_AGENT_PIN = "0000"


def build_pairing_agent_class() -> type[Any]:
    """Return the agent service class (dbus-fast is imported lazily)."""
    from dbus_fast.service import ServiceInterface, method  # noqa: PLC0415

    class PairingAgent(ServiceInterface):
        """Accepts every pairing request and answers PIN prompts with ``pin``."""

        def __init__(self, pin: str = DEFAULT_AGENT_PIN) -> None:
            super().__init__("org.bluez.Agent1")
            self.pin = pin

        @method()
        def Release(self):
            """Bluez dropped the agent; nothing to clean up."""

        @method()
        def RequestPinCode(self, device: "o") -> "s":
            return self.pin

        @method()
        def DisplayPinCode(self, device: "o", pincode: "s"):
            """Printers have no display; nothing to show."""

        @method()
        def RequestPasskey(self, device: "o") -> "u":
            return int(self.pin) if self.pin.isdigit() else 0

        @method()
        def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
            """Printers have no keypad; nothing to show."""

        @method()
        def RequestConfirmation(self, device: "o", passkey: "u"):
            """Numeric comparison: returning without an error accepts."""

        @method()
        def RequestAuthorization(self, device: "o"):
            """Accept an incoming pairing request."""

        @method()
        def AuthorizeService(self, device: "o", uuid: "s"):
            """Accept service authorization (e.g. Serial Port Profile)."""

        @method()
        def Cancel(self):
            """Bluez cancelled the request in flight."""

    return PairingAgent
