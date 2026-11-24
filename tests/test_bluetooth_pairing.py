"""Tests for Bluetooth scanning and pairing (bluez D-Bus layer + config-flow steps)."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from dbus_fast import DBusError
from dbus_fast.service import ServiceInterface
import pytest

from custom_components.escpos_printer import bluez_pairing
from custom_components.escpos_printer._bluez_agent import build_pairing_agent_class
from custom_components.escpos_printer._config_flow import bluetooth_helpers
from custom_components.escpos_printer.bluez import parse_bluez_devices
from custom_components.escpos_printer.bluez_pairing import (
    PAIR_ERROR_AUTH_FAILED,
    PAIR_ERROR_FAILED,
    PAIR_ERROR_NOT_FOUND,
    PAIR_ERROR_TIMEOUT,
    PAIR_ERROR_UNAVAILABLE,
    PairingResult,
    classify_bluez_error,
)
from custom_components.escpos_printer.config_flow import EscposConfigFlow
from custom_components.escpos_printer.const import (
    BT_SCAN_KEY,
    CONF_BT_PIN,
    CONF_CONNECTION_TYPE,
    CONNECTION_TYPE_BLUETOOTH,
)

STEPS = "custom_components.escpos_printer._config_flow.bluetooth_steps."
PRINTER_MAC = "AA:BB:CC:DD:EE:FF"


def _gated(result):
    """Return ``(coroutine_fn, gate)``: the coroutine only finishes once ``gate`` is set.

    Home Assistant starts tasks eagerly, so an instantly-resolving mock would
    already be done on the first step call and skip the progress dialog.
    """
    gate = asyncio.Event()

    async def run(*_args, **_kwargs):
        await gate.wait()
        if isinstance(result, Exception):
            raise result
        return result

    return run, gate


def _call_agent(agent, method_name, *args):
    """Invoke an agent method's real body (dbus-fast's decorator swallows return values)."""
    method = next(m for m in ServiceInterface._get_methods(agent) if m.name == method_name)
    return method.fn(agent, *args)


def _var(value):
    """Stand-in for a dbus-fast ``Variant`` (only ``.value`` is read)."""
    return SimpleNamespace(value=value)


def _managed_device(mac, *, paired, name="Netum NT-1809DD", cls=0x680, rssi=-60):
    return {
        "Address": _var(mac),
        "Alias": _var(name),
        "Paired": _var(paired),
        "Class": _var(cls),
        "RSSI": _var(rssi),
    }


def _scan_device(mac=PRINTER_MAC, *, paired=False, name="Netum NT-1809DD"):
    return {
        "mac": mac,
        "name": name,
        "alias": name,
        "label": f"{name} ({mac})",
        "class": 0x680,
        "is_imaging": True,
        "has_spp": False,
        "paired": paired,
        "rssi": -60,
        "_choice_key": mac,
    }


class TestParseBluezDevices:
    def test_marks_paired_state_and_rssi(self):
        managed = {
            "/org/bluez/hci0/dev_A": {
                "org.bluez.Device1": _managed_device(PRINTER_MAC, paired=False)
            },
            "/org/bluez/hci0/dev_B": {
                "org.bluez.Device1": _managed_device("11:22:33:44:55:66", paired=True)
            },
        }
        devices = parse_bluez_devices(managed, paired_only=False)
        by_mac = {d["mac"]: d for d in devices}
        assert by_mac[PRINTER_MAC]["paired"] is False
        assert by_mac[PRINTER_MAC]["rssi"] == -60
        assert by_mac["11:22:33:44:55:66"]["paired"] is True

    def test_paired_only_skips_discovered_devices(self):
        managed = {
            "/dev_A": {"org.bluez.Device1": _managed_device(PRINTER_MAC, paired=False)},
            "/dev_B": {"org.bluez.Device1": _managed_device("11:22:33:44:55:66", paired=True)},
        }
        devices = parse_bluez_devices(managed)
        assert [d["mac"] for d in devices] == ["11:22:33:44:55:66"]

    def test_ignores_invalid_addresses_and_foreign_objects(self):
        managed = {
            "/adapter": {"org.bluez.Adapter1": {}},
            "/dev": {"org.bluez.Device1": _managed_device("garbage", paired=True)},
        }
        assert parse_bluez_devices(managed, paired_only=False) == []


class TestErrorMapping:
    @pytest.mark.parametrize(
        ("bluez_error", "expected"),
        [
            ("org.bluez.Error.AuthenticationFailed", PAIR_ERROR_AUTH_FAILED),
            ("org.bluez.Error.AuthenticationTimeout", PAIR_ERROR_TIMEOUT),
            ("org.bluez.Error.DoesNotExist", PAIR_ERROR_NOT_FOUND),
            ("org.bluez.Error.Whatever", PAIR_ERROR_FAILED),
            (None, PAIR_ERROR_FAILED),
        ],
    )
    def test_classify_bluez_error(self, bluez_error, expected):
        assert classify_bluez_error(bluez_error) == expected

    def test_every_pair_error_has_a_form_error_key(self):
        for code in (PAIR_ERROR_AUTH_FAILED, PAIR_ERROR_TIMEOUT, PAIR_ERROR_UNAVAILABLE):
            assert bluetooth_helpers._pair_error_to_key(code).startswith("bt_pair_")
        assert bluetooth_helpers._pair_error_to_key("nonsense") == "bt_pair_failed"


class TestPairingAgent:
    def test_answers_pin_and_passkey_requests(self):
        agent = build_pairing_agent_class()("1234")
        assert _call_agent(agent, "RequestPinCode", "/dev") == "1234"
        assert _call_agent(agent, "RequestPasskey", "/dev") == 1234

    def test_non_numeric_pin_gives_zero_passkey(self):
        agent = build_pairing_agent_class()("abcd")
        assert _call_agent(agent, "RequestPasskey", "/dev") == 0

    def test_exports_the_bluez_agent_interface(self):
        agent = build_pairing_agent_class()()
        names = {m.name for m in agent.introspect().methods}
        assert {"RequestPinCode", "RequestConfirmation", "AuthorizeService", "Cancel"} <= names


class TestCallPair:
    @pytest.mark.asyncio
    async def test_success(self):
        device = SimpleNamespace(call_pair=AsyncMock())
        assert (await bluez_pairing._call_pair(device, 1.0)).success is True

    @pytest.mark.asyncio
    async def test_already_exists_counts_as_success(self):
        device = SimpleNamespace(
            call_pair=AsyncMock(side_effect=DBusError("org.bluez.Error.AlreadyExists", "x"))
        )
        assert (await bluez_pairing._call_pair(device, 1.0)).success is True

    @pytest.mark.asyncio
    async def test_bluez_error_is_classified(self):
        device = SimpleNamespace(
            call_pair=AsyncMock(side_effect=DBusError("org.bluez.Error.AuthenticationFailed", "x"))
        )
        result = await bluez_pairing._call_pair(device, 1.0)
        assert result == PairingResult(False, PAIR_ERROR_AUTH_FAILED)

    @pytest.mark.asyncio
    async def test_timeout_cancels_pairing(self):
        async def hang():

            await asyncio.sleep(10)

        device = SimpleNamespace(call_pair=hang, call_cancel_pairing=AsyncMock())
        result = await bluez_pairing._call_pair(device, 0.01)
        assert result == PairingResult(False, PAIR_ERROR_TIMEOUT)
        device.call_cancel_pairing.assert_awaited_once()


class TestPairWithPins:
    @pytest.fixture
    def bus(self):
        return MagicMock()

    @pytest.fixture
    def manager(self):
        return SimpleNamespace(call_register_agent=AsyncMock(), call_unregister_agent=AsyncMock())

    @pytest.mark.asyncio
    async def test_tries_next_pin_after_auth_failure(self, bus, manager):
        seen_pins = []
        agent_holder = {}
        real_cls = build_pairing_agent_class()

        def make_agent():
            agent_holder["agent"] = real_cls()
            return agent_holder["agent"]

        async def pair_attempt(_device, _timeout):
            seen_pins.append(agent_holder["agent"].pin)
            if len(seen_pins) == 1:
                return PairingResult(False, PAIR_ERROR_AUTH_FAILED)
            return PairingResult(True)

        with (
            patch.object(bluez_pairing, "build_pairing_agent_class", return_value=make_agent),
            patch.object(bluez_pairing, "_proxy_interface", AsyncMock(return_value=manager)),
            patch.object(bluez_pairing, "_call_pair", pair_attempt),
        ):
            result = await bluez_pairing._pair_with_pins(bus, object(), ("0000", "1234"), 5.0)

        assert result.success is True
        assert seen_pins == ["0000", "1234"]
        manager.call_register_agent.assert_awaited_once()
        manager.call_unregister_agent.assert_awaited_once()
        bus.unexport.assert_called_once_with(bluez_pairing.AGENT_PATH)

    @pytest.mark.asyncio
    async def test_other_errors_stop_immediately(self, bus, manager):
        attempts = AsyncMock(return_value=PairingResult(False, PAIR_ERROR_TIMEOUT))
        with (
            patch.object(bluez_pairing, "_proxy_interface", AsyncMock(return_value=manager)),
            patch.object(bluez_pairing, "_call_pair", attempts),
        ):
            result = await bluez_pairing._pair_with_pins(bus, object(), ("0000", "1234"), 5.0)

        assert result.error == PAIR_ERROR_TIMEOUT
        assert attempts.await_count == 1


class TestPairBluetoothDevice:
    @pytest.mark.asyncio
    async def test_invalid_mac(self):
        assert (await bluez_pairing.pair_bluetooth_device("nope")).error == PAIR_ERROR_NOT_FOUND

    @pytest.mark.asyncio
    async def test_no_system_bus(self):
        with patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=None)):
            result = await bluez_pairing.pair_bluetooth_device(PRINTER_MAC)
        assert result.error == PAIR_ERROR_UNAVAILABLE

    @pytest.mark.asyncio
    async def test_unknown_device(self):
        bus = MagicMock()
        with (
            patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=bus)),
            patch.object(bluez_pairing, "_get_managed_objects", AsyncMock(return_value={})),
        ):
            result = await bluez_pairing.pair_bluetooth_device(PRINTER_MAC)
        assert result.error == PAIR_ERROR_NOT_FOUND
        bus.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_already_paired_device_is_only_trusted(self):
        bus = MagicMock()
        device = SimpleNamespace(set_trusted=AsyncMock(), call_pair=AsyncMock())
        managed = {"/dev": {"org.bluez.Device1": _managed_device(PRINTER_MAC, paired=True)}}
        with (
            patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=bus)),
            patch.object(bluez_pairing, "_get_managed_objects", AsyncMock(return_value=managed)),
            patch.object(bluez_pairing, "_proxy_interface", AsyncMock(return_value=device)),
        ):
            result = await bluez_pairing.pair_bluetooth_device(PRINTER_MAC)
        assert result.success is True
        device.set_trusted.assert_awaited_once_with(True)
        device.call_pair.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_successful_pairing_trusts_the_device(self):
        bus = MagicMock()
        device = SimpleNamespace(set_trusted=AsyncMock())
        managed = {"/dev": {"org.bluez.Device1": _managed_device(PRINTER_MAC, paired=False)}}
        with (
            patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=bus)),
            patch.object(bluez_pairing, "_get_managed_objects", AsyncMock(return_value=managed)),
            patch.object(bluez_pairing, "_proxy_interface", AsyncMock(return_value=device)),
            patch.object(
                bluez_pairing, "_pair_with_pins", AsyncMock(return_value=PairingResult(True))
            ) as pair,
        ):
            result = await bluez_pairing.pair_bluetooth_device(PRINTER_MAC, pin="4321")
        assert result.success is True
        assert pair.await_args.args[2] == ("4321",)
        device.set_trusted.assert_awaited_once_with(True)


class TestDiscovery:
    @pytest.mark.asyncio
    async def test_no_bus_returns_empty(self):
        with patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=None)):
            assert await bluez_pairing.discover_bluetooth_devices(0) == []

    @pytest.mark.asyncio
    async def test_no_adapter_returns_empty(self):
        with (
            patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=MagicMock())),
            patch.object(bluez_pairing, "_get_managed_objects", AsyncMock(return_value={})),
        ):
            assert await bluez_pairing.discover_bluetooth_devices(0) == []

    @pytest.mark.asyncio
    async def test_lists_paired_first_then_by_signal(self):
        managed = {
            "/hci0": {"org.bluez.Adapter1": {}},
            "/dev_weak": {
                "org.bluez.Device1": _managed_device("00:00:00:00:00:01", paired=False, rssi=-90)
            },
            "/dev_strong": {
                "org.bluez.Device1": _managed_device("00:00:00:00:00:02", paired=False, rssi=-40)
            },
            "/dev_paired": {
                "org.bluez.Device1": _managed_device("00:00:00:00:00:03", paired=True, rssi=-99)
            },
        }
        with (
            patch.object(bluez_pairing, "_connect_system_bus", AsyncMock(return_value=MagicMock())),
            patch.object(bluez_pairing, "_get_managed_objects", AsyncMock(return_value=managed)),
            patch.object(bluez_pairing, "_run_inquiry", AsyncMock()) as inquiry,
        ):
            devices = await bluez_pairing.discover_bluetooth_devices(0)
        assert [d["mac"] for d in devices] == [
            "00:00:00:00:00:03",
            "00:00:00:00:00:02",
            "00:00:00:00:00:01",
        ]
        inquiry.assert_awaited_once()


class TestPickerChoices:
    def test_unpaired_devices_are_labelled_and_scan_is_offered(self):
        choices = bluetooth_helpers._build_bt_device_choices([_scan_device(paired=False)])
        assert choices[PRINTER_MAC].endswith("not paired yet")
        assert BT_SCAN_KEY in choices

    def test_known_printer_name_keeps_unclassified_device_in_the_list(self):
        device = _scan_device(paired=False)
        device.update(is_imaging=False, is_known_printer=True)
        phone = _scan_device("11:22:33:44:55:66", name="Pixel 8")
        phone.update(is_imaging=False)
        choices = bluetooth_helpers._build_bt_device_choices([device, phone])
        assert PRINTER_MAC in choices
        assert "11:22:33:44:55:66" not in choices


def _new_flow(hass):
    flow = EscposConfigFlow()
    flow.hass = hass
    flow._user_data = {CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH}
    return flow


class TestScanStep:
    @pytest.mark.asyncio
    async def test_scan_shows_progress_then_returns_to_picker(self, hass):
        flow = _new_flow(hass)
        scan, gate = _gated([_scan_device()])
        with patch(STEPS + "_scan_bluetooth_devices", scan):
            first = await flow.async_step_bluetooth_scan()
            assert first["type"] == "progress"
            assert first["progress_action"] == "bluetooth_scan"
            gate.set()
            await flow._bt_task
            done = await flow.async_step_bluetooth_scan()

        assert done["type"] == "progress_done"
        assert done["step_id"] == "bluetooth_select"
        assert flow._paired_bt_devices[0]["mac"] == PRINTER_MAC
        assert flow._bt_task is None

    @pytest.mark.asyncio
    async def test_empty_scan_falls_back_to_the_menu(self, hass):
        flow = _new_flow(hass)
        scan, gate = _gated([])
        with patch(STEPS + "_scan_bluetooth_devices", scan):
            await flow.async_step_bluetooth_scan()
            gate.set()
            await flow._bt_task
            done = await flow.async_step_bluetooth_scan()
        assert done["step_id"] == "bluetooth_no_devices"

    @pytest.mark.asyncio
    async def test_crashed_scan_is_treated_as_empty(self, hass):
        flow = _new_flow(hass)
        scan, gate = _gated(RuntimeError("boom"))
        with patch(STEPS + "_scan_bluetooth_devices", scan):
            await flow.async_step_bluetooth_scan()
            gate.set()
            await asyncio.gather(flow._bt_task, return_exceptions=True)
            done = await flow.async_step_bluetooth_scan()
        assert done["step_id"] == "bluetooth_no_devices"

    @pytest.mark.asyncio
    async def test_picker_offers_scan_and_routes_to_it(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=True)]
        scan, gate = _gated([])
        with patch(STEPS + "_scan_bluetooth_devices", scan):
            result = await flow.async_step_bluetooth_select({"bt_device": BT_SCAN_KEY})
            gate.set()
            await flow._bt_task
        assert result["type"] == "progress"
        assert result["step_id"] == "bluetooth_scan"

    @pytest.mark.asyncio
    async def test_closing_the_dialog_cancels_a_running_task(self, hass):
        flow = _new_flow(hass)
        scan, _gate = _gated([])
        with patch(STEPS + "_scan_bluetooth_devices", scan):
            await flow.async_step_bluetooth_scan()
            task = flow._bt_task
            flow.async_remove()
            await asyncio.gather(task, return_exceptions=True)
        assert task.cancelled()


SELECT_INPUT = {
    "bt_device": PRINTER_MAC,
    "timeout": 4.0,
    "profile": "",
    "advanced_options": {"rfcomm_channel": 1},
}


class TestPairStep:
    @pytest.mark.asyncio
    async def test_unpaired_selection_starts_pairing(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=False)]
        pair, gate = _gated(PairingResult(True))
        with patch(STEPS + "_pair_bluetooth_device", pair):
            result = await flow.async_step_bluetooth_select(SELECT_INPUT)
            assert result["type"] == "progress"
            assert result["progress_action"] == "bluetooth_pair"
            assert flow._pending_bt["mac"] == PRINTER_MAC
            gate.set()
            await flow._bt_task

    @pytest.mark.asyncio
    async def test_paired_selection_skips_pairing(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=True)]
        pair = AsyncMock()
        with (
            patch(STEPS + "_pair_bluetooth_device", pair),
            patch(STEPS + "_can_connect_bluetooth", return_value=(True, None, None)),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_select(SELECT_INPUT)
        pair.assert_not_awaited()
        assert result["step_id"] == "codepage"

    @pytest.mark.asyncio
    async def test_successful_pairing_continues_to_printer_settings(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=False)]
        pair, gate = _gated(PairingResult(True))
        with (
            patch(STEPS + "_pair_bluetooth_device", pair),
            patch(STEPS + "_can_connect_bluetooth", return_value=(True, None, None)),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            await flow.async_step_bluetooth_select(SELECT_INPUT)
            gate.set()
            await flow._bt_task
            done = await flow.async_step_bluetooth_pair()
            assert done["type"] == "progress_done"
            assert done["step_id"] == "bluetooth_pair_finish"
            result = await flow.async_step_bluetooth_pair_finish()

        assert result["step_id"] == "codepage"
        assert flow._paired_bt_devices[0]["paired"] is True
        assert flow._user_data["bt_mac"] == PRINTER_MAC

    @pytest.mark.asyncio
    async def test_refused_pins_ask_the_user(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=False)]
        flow._pending_bt = {"mac": PRINTER_MAC, "printer_name": "Netum"}
        flow._bt_pair_result = PairingResult(False, PAIR_ERROR_AUTH_FAILED)
        result = await flow.async_step_bluetooth_pair_finish()
        assert result["type"] == "form"
        assert result["step_id"] == "bluetooth_pin"
        assert "errors" not in result or not result["errors"]

    @pytest.mark.asyncio
    async def test_entered_pin_is_used_for_the_next_attempt(self, hass):
        flow = _new_flow(hass)
        flow._pending_bt = {"mac": PRINTER_MAC, "printer_name": "Netum"}
        calls = []
        run, gate = _gated(PairingResult(True))

        async def pair(mac, pin=None):
            calls.append((mac, pin))
            return await run()

        with patch(STEPS + "_pair_bluetooth_device", pair):
            result = await flow.async_step_bluetooth_pin({CONF_BT_PIN: " 9876 "})
            assert result["type"] == "progress"
            gate.set()
            await flow._bt_task
        assert calls == [(PRINTER_MAC, "9876")]

    @pytest.mark.asyncio
    async def test_pin_form_flags_a_pin_that_was_refused_again(self, hass):
        flow = _new_flow(hass)
        flow._pending_bt = {"mac": PRINTER_MAC, "printer_name": "Netum", "pin": "1111"}
        result = await flow.async_step_bluetooth_pin()
        assert result["errors"]["base"] == "bt_pair_auth_failed"

    @pytest.mark.asyncio
    async def test_other_pairing_failures_return_to_the_picker_with_an_error(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=False)]
        flow._pending_bt = {"mac": PRINTER_MAC, "printer_name": "Netum"}
        flow._bt_pair_result = PairingResult(False, PAIR_ERROR_TIMEOUT)
        result = await flow.async_step_bluetooth_pair_finish()
        assert result["step_id"] == "bluetooth_select"
        assert result["errors"]["base"] == "bt_pair_timeout"
        # The error is shown once, not on every later render.
        again = await flow.async_step_bluetooth_select()
        assert not again["errors"]

    @pytest.mark.asyncio
    async def test_probe_failure_after_pairing_returns_to_the_picker(self, hass):
        flow = _new_flow(hass)
        flow._paired_bt_devices = [_scan_device(paired=False)]
        flow._pending_bt = {
            "mac": PRINTER_MAC,
            "channel": 1,
            "timeout": 4.0,
            "profile": "",
            "printer_name": "Netum",
        }
        flow._bt_pair_result = PairingResult(True)
        with (
            patch(STEPS + "_can_connect_bluetooth", return_value=(False, "host_down", None)),
            patch.object(flow, "async_set_unique_id", return_value=None),
            patch.object(flow, "_abort_if_unique_id_configured"),
        ):
            result = await flow.async_step_bluetooth_pair_finish()
        assert result["step_id"] == "bluetooth_select"
        assert result["errors"]["base"] == "bt_host_down"


class TestFlowHelpers:
    @pytest.mark.asyncio
    async def test_scan_flags_devices_with_known_printer_names(self, hass):
        found = [
            _scan_device(name="Netum NT-1809DD"),
            _scan_device("11:22:33:44:55:66", name="Pixel 8"),
        ]
        with patch.object(
            bluetooth_helpers, "discover_bluetooth_devices", AsyncMock(return_value=found)
        ):
            devices = await bluetooth_helpers._scan_bluetooth_devices(hass)
        assert [d["is_known_printer"] for d in devices] == [True, False]

    @pytest.mark.asyncio
    async def test_pair_helper_forwards_mac_and_pin(self):
        with patch.object(
            bluetooth_helpers, "pair_bluetooth_device", AsyncMock(return_value=PairingResult(True))
        ) as pair:
            result = await bluetooth_helpers._pair_bluetooth_device(PRINTER_MAC, "1234")
        assert result.success is True
        pair.assert_awaited_once_with(PRINTER_MAC, pin="1234")
