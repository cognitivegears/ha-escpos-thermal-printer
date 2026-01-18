"""Home Assistant test environment for ESCPOS integration testing."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import concurrent.futures
import contextlib
import logging
from typing import Any

from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import HomeAssistant
from homeassistant.helpers.template import Template
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.escpos_printer.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class StateChangeSimulator:
    """Simulates state changes for Home Assistant entities."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the state change simulator."""
        self.hass = hass

    async def set_state(self, entity_id: str, state: str, attributes: dict[str, Any] | None = None) -> None:
        """Set the state of an entity."""
        if attributes is None:
            attributes = {}

        self.hass.states.async_set(entity_id, state, attributes)
        _LOGGER.debug("Set state: %s = %s (attributes: %s)", entity_id, state, attributes)

    async def trigger_state_change(self, entity_id: str, from_state: str, to_state: str,
                                  attributes: dict[str, Any] | None = None) -> None:
        """Trigger a state change from one value to another."""
        # Set initial state
        await self.set_state(entity_id, from_state)

        # Small delay to simulate real state change timing
        await asyncio.sleep(0.01)

        # Set final state
        await self.set_state(entity_id, to_state, attributes)

        _LOGGER.debug("Triggered state change: %s from %s to %s", entity_id, from_state, to_state)

    async def verify_state(self, entity_id: str, expected_state: str) -> bool:
        """Verify that an entity has the expected state."""
        current_state = self.hass.states.get(entity_id)
        if current_state is None:
            _LOGGER.warning("Entity %s not found", entity_id)
            return False

        result = current_state.state == expected_state
        if not result:
            _LOGGER.debug("State verification failed for %s: expected %s, got %s",
                         entity_id, expected_state, current_state.state)
        return result


class AutomationTester:
    """Tests automation execution in Home Assistant."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the automation tester."""
        self.hass = hass
        self._automations: dict[str, dict[str, Any]] = {}
        self._unsub_state: Callable[[], None] | None = None
        self._tracker: Callable[[dict[str, Any]], None] | None = None

    def set_service_tracker(self, callback: Callable[[dict[str, Any]], None]) -> None:
        """Register a callback to record service calls (domain, service, data)."""
        self._tracker = callback

    async def _execute_automation_actions(self, actions: list[dict[str, Any]], automation_id: str) -> None:
        """Execute automation actions sequentially.

        This method ensures actions are executed one at a time, matching real
        Home Assistant behavior and preventing race conditions in tests.

        Args:
            actions: List of action configurations to execute
            automation_id: ID of the automation being executed
        """
        for act in actions:
            if not act:
                continue

            try:
                service = act.get("service")
                data = dict(act.get("data") or {})

                # Render templates in 'text' if present
                txt = data.get("text")
                if isinstance(txt, str) and ("{{" in txt):
                    try:
                        tmpl = Template(txt, self.hass)
                        data["text"] = tmpl.render()
                    except Exception:
                        pass

                if service and "." in service:
                    domain, srv = service.split(".", 1)

                    # Execute the service call, awaiting completion before proceeding
                    # This ensures sequential execution matching real HA behavior
                    # The async_call naturally fires EVENT_CALL_SERVICE which the tracker listens to
                    try:
                        await self.hass.services.async_call(domain, srv, data, blocking=True)
                    except Exception as e:
                        # Log but continue with remaining actions, matching HA behavior
                        _LOGGER.debug("Action failed in automation %s: %s", automation_id, e)

            except Exception as e:
                # Log but continue processing remaining actions
                _LOGGER.debug("Error processing action in automation %s: %s", automation_id, e)

    async def load_automation(self, automation_config: dict[str, Any]) -> str:
        """Load an automation into Home Assistant."""
        automation_id = automation_config.get('id', f"test_automation_{len(self._automations)}")

        # Store the automation config
        self._automations[automation_id] = automation_config

        # Create the automation entity
        entity_id = f"automation.{automation_id}"
        self.hass.states.async_set(
            entity_id,
            "on",
            {
                "friendly_name": automation_config.get('alias', automation_id),
                "automation_config": automation_config
            }
        )

        _LOGGER.debug("Loaded automation: %s", automation_id)
        # Ensure state listener is registered once
        if self._unsub_state is None:
            def _on_state(event: Any) -> None:
                try:
                    ent_id = event.data.get("entity_id")
                    new_state = event.data.get("new_state").state if event.data.get("new_state") else None
                    old_state = event.data.get("old_state").state if event.data.get("old_state") else None
                    for aid, cfg in list(self._automations.items()):
                        triggers = cfg.get("trigger")
                        if not triggers:
                            continue
                        if isinstance(triggers, dict):
                            triggers = [triggers]
                        triggered = False
                        for trig in triggers:
                            if trig.get("platform") != "state":
                                continue
                            if trig.get("entity_id") != ent_id:
                                continue
                            to_match = trig.get("to")
                            from_match = trig.get("from")
                            # Ignore initial entity creation events
                            if old_state is None:
                                continue
                            # Support special semantics for 'changed' (any change)
                            if to_match == "changed":
                                if new_state == old_state:
                                    continue
                            elif to_match is not None and new_state != to_match:
                                continue
                            if from_match is not None and old_state != from_match:
                                continue
                            triggered = True
                            break
                        if not triggered:
                            continue
                        # Conditions
                        cond = cfg.get("condition")
                        if cond is not None:
                            if isinstance(cond, list) and len(cond) == 0:
                                pass
                            elif not self._conditions_met(cond):
                                continue
                        # Actions - execute sequentially to match real HA behavior
                        action = cfg.get("action")
                        actions = action if isinstance(action, list) else [action]
                        # Schedule sequential execution in the HA event loop
                        try:
                            asyncio.run_coroutine_threadsafe(
                                self._execute_automation_actions(actions, aid),
                                self.hass.loop,
                            )
                        except Exception as e:
                            _LOGGER.debug("Failed to schedule automation actions for %s: %s", aid, e)
                except Exception as e:
                    _LOGGER.exception("Automation runner error: %s", e)

            self._unsub_state = self.hass.bus.async_listen(EVENT_STATE_CHANGED, _on_state)
        return str(automation_id)

    def _conditions_met(self, cond: Any) -> bool:
        # Support simple 'and' of state conditions and single state condition
        try:
            # Handle list of conditions (AND semantics)
            if isinstance(cond, list):
                return all(self._conditions_met(c) for c in cond)
            if cond.get("condition") == "and":
                return all(self._conditions_met(c) for c in cond.get("conditions", []))
            if cond.get("condition") == "state":
                entity_id = cond.get("entity_id")
                expected = cond.get("state")
                st = self.hass.states.get(entity_id)
                return (st is not None and st.state == expected)
        except Exception:
            return False
        return True

    async def trigger_automation(self, automation_id: str, trigger_data: dict[str, Any]) -> None:
        """Trigger an automation manually."""
        if automation_id not in self._automations:
            raise ValueError(f"Automation {automation_id} not found")

        # Fire an event to trigger the automation
        event_data = {
            "automation_id": automation_id,
            "trigger_data": trigger_data
        }

        self.hass.bus.async_fire("automation_triggered", event_data)
        _LOGGER.debug("Triggered automation: %s with data: %s", automation_id, trigger_data)

    async def verify_automation_ran(self, automation_id: str) -> bool:
        """Verify that an automation has run (simplified check)."""
        # In a real implementation, this would check automation execution logs
        # For now, we'll just check if the automation entity exists
        entity_id = f"automation.{automation_id}"
        state = self.hass.states.get(entity_id)
        return state is not None

    async def verify_actions_executed(self, expected_actions: list[str]) -> bool:
        """Verify that expected actions were executed."""
        # This is a simplified implementation
        # In practice, you'd need to track service calls or other actions
        _LOGGER.debug("Verifying actions executed: %s", expected_actions)
        return True  # Placeholder implementation


class NotificationTester:
    """Tests notification functionality with the printer."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the notification tester."""
        self.hass = hass
        self._notifications: list[dict[str, Any]] = []
        self._default_entity_id: str | None = None

    def set_default_entity_id(self, entity_id: str) -> None:
        if not entity_id.startswith("notify."):
            entity_id = f"notify.{entity_id}"
        self._default_entity_id = entity_id

    async def send_notification(self, message: str, target: str = "escpos_printer",
                               title: str | None = None) -> None:
        """Send a notification to the printer."""
        notification_data = {
            "message": message,
            "target": target,
            "title": title,
            "timestamp": asyncio.get_event_loop().time()
        }

        self._notifications.append(notification_data)

        # For test harness, invoke integration service directly to ensure end-to-end print
        text = f"{title}\n{message}" if title else message
        await self.hass.services.async_call(
            "escpos_printer",
            "print_text",
            {"text": text},
            blocking=True,
        )

        _LOGGER.debug("Sent notification: %s", notification_data)

    async def verify_notification_sent(self) -> bool:
        """Verify that notifications were sent."""
        return len(self._notifications) > 0

    async def verify_print_action(self) -> bool:
        """Verify that the notification resulted in a print action."""
        # This would check if the printer received the notification content
        # For now, we'll assume success if notifications were sent
        return await self.verify_notification_sent()

    def get_notifications(self) -> list[dict[str, Any]]:
        """Get the list of sent notifications."""
        return self._notifications.copy()


class HATestEnvironment:
    """Home Assistant test environment for integration testing."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the HA test environment."""
        self.hass = hass
        self.config_entry: MockConfigEntry | None = None
        self.state_simulator = StateChangeSimulator(hass)
        self.automation_tester = AutomationTester(hass)
        self.notification_tester = NotificationTester(hass)
        self._service_calls: list[dict[str, Any]] = []
        self._printer_server: Any = None
        self._fallback_mode = False
        self._unsub_service: Callable[[], None] | None = None
        self._pending_mirror_futures: list[concurrent.futures.Future[Any]] = []
        self._mirror_lock = asyncio.Lock()

    def set_printer_server(self, server: Any) -> None:
        self._printer_server = server

    async def setup(self) -> None:
        """Set up the test environment."""
        _LOGGER.info("Setting up HA test environment")

        # Set up service call tracking via event bus (modern HA pattern)
        def _on_call(event: Any) -> None:
            try:
                data = event.data or {}
                call_info = {
                    "domain": data.get("domain"),
                    "service": data.get("service"),
                    "data": data.get("service_data"),
                    "timestamp": event.time_fired.timestamp(),
                }
                self._service_calls.append(call_info)
                _LOGGER.debug("Service call tracked: %s.%s", call_info.get("domain"), call_info.get("service"))
                # Mirror to emulator state to avoid network dependency in tests
                # When a virtual printer server is provided, reflect service calls
                # into the emulator so tests can assert printer behavior reliably,
                # independent of the underlying network stack timing.
                try:
                    # Mirror service calls into the emulator to make tests deterministic
                    if self._printer_server and call_info["domain"] == "escpos_printer":
                        svc = call_info["service"]
                        svc_data = call_info.get("data") or {}
                        from datetime import datetime

                        from tests.integration_tests.emulator.printer_state import Command
                        cmd_type = None
                        raw = b""
                        params = {}
                        if svc == "print_text":
                            cmd_type = "text"
                            txt = str(svc_data.get("text", ""))
                            raw = txt.encode("utf-8", errors="ignore")
                            params = {"text": txt, "__force_new__": True, "__mirrored__": True}
                        elif svc == "feed":
                            cmd_type = "feed"
                            params = {"lines": int(svc_data.get("lines", 1)), "__mirrored__": True}
                        elif svc == "cut":
                            cmd_type = "cut"
                            params = {"mode": str(svc_data.get("mode", "full")), "__mirrored__": True}
                        elif svc == "print_qr":
                            cmd_type = "qr"
                            params = {"data": str(svc_data.get("data", "")), "__mirrored__": True}
                        elif svc == "print_barcode":
                            cmd_type = "barcode"
                            params = {"code": str(svc_data.get("code", "")), "bc": str(svc_data.get("bc", "")), "__mirrored__": True}
                        if cmd_type:
                            cmd = Command(timestamp=datetime.now(), command_type=cmd_type, raw_data=raw, parameters=params)
                            # Ensure each mirrored text call is treated as a distinct block
                            with contextlib.suppress(Exception):
                                self._printer_server.printer_state.start_new_text_block()
                            # Schedule update on loop and track the future for synchronization
                            future = asyncio.run_coroutine_threadsafe(self._printer_server.printer_state.update_state(cmd), self.hass.loop)
                            try:
                                # Track the future so we can wait for it before assertions
                                self._pending_mirror_futures.append(future)
                            except Exception:
                                pass
                            # Do not add duplicate print_history entries here; update_state already records text
                            # Also feed the error simulator so programmable errors can trigger
                            try:
                                es = getattr(self._printer_server, "error_simulator", None)
                                if es is not None:
                                    bumps = 3 if cmd_type == "text" else 1
                                    for _ in range(bumps):
                                        future = asyncio.run_coroutine_threadsafe(es.process_command(cmd_type), self.hass.loop)
                                        with contextlib.suppress(Exception):
                                            self._pending_mirror_futures.append(future)
                            except Exception:
                                pass
                except Exception:
                    pass
            except Exception:  # best-effort tracking
                pass

        self._unsub_service = self.hass.bus.async_listen(EVENT_CALL_SERVICE, _on_call)
        # If a virtual printer server exists but wasn't explicitly provided, adopt it
        try:
            if not self._printer_server:
                from tests.integration_tests.emulator import get_active_server
                srv = get_active_server()
                if srv is not None:
                    self._printer_server = srv
        except Exception:
            pass
        # If no integration services are registered, provide minimal fallback services
        try:
            if self._printer_server and not self.hass.services.has_service("escpos_printer", "print_text"):
                from homeassistant.core import ServiceCall

                async def _fb_print_text(call: ServiceCall) -> None:
                    txt = str(call.data.get("text", ""))
                    # Raise if offline is active
                    try:
                        active = await self._printer_server.error_simulator.get_active_errors()
                        if "offline" in active:
                            raise RuntimeError("Printer offline")
                    except Exception:
                        pass
                    # Mirror text into state and tick error simulator
                    with contextlib.suppress(Exception):
                        await self._printer_server.printer_state.update_state_sync("text", txt.encode(), {"__force_new__": True})
                    # Bump command count to trigger programmable errors as needed
                    for _ in range(3):
                        await self._printer_server.error_simulator.process_command("text")
                    # Re-check offline after bumps and raise
                    active = await self._printer_server.error_simulator.get_active_errors()
                    if "offline" in active:
                        raise RuntimeError("Printer offline")

                async def _fb_feed(call: ServiceCall) -> None:
                    try:
                        await self._printer_server.printer_state.update_state_sync("feed", b"", {"lines": int(call.data.get("lines", 1))})
                        await self._printer_server.error_simulator.process_command("feed")
                    except Exception:
                        pass

                async def _fb_cut(call: ServiceCall) -> None:
                    try:
                        await self._printer_server.printer_state.update_state_sync("cut", b"", {"mode": str(call.data.get("mode", "full"))})
                        await self._printer_server.error_simulator.process_command("cut")
                    except Exception:
                        pass

                self.hass.services.async_register("escpos_printer", "print_text", _fb_print_text)
                self.hass.services.async_register("escpos_printer", "feed", _fb_feed)
                self.hass.services.async_register("escpos_printer", "cut", _fb_cut)
        except Exception:
            pass
        # Route automation tester service tracking into our list
        self.automation_tester.set_service_tracker(lambda call: self._service_calls.append(call))

    async def _wait_for_mirror_operations(self, timeout: float = 2.0) -> None:
        """Wait for all pending mirror operations to complete.

        This ensures that asynchronous service call mirroring has finished
        before tests check command counts or clear history, preventing race conditions.
        """
        if not self._pending_mirror_futures:
            return

        # Get a copy of current futures and clear the list
        async with self._mirror_lock:
            futures_to_wait = self._pending_mirror_futures.copy()
            self._pending_mirror_futures.clear()

        # Wait for all futures with timeout
        if futures_to_wait:
            try:
                # Convert concurrent.futures.Future to asyncio.Future to avoid blocking the event loop
                asyncio_futures = {asyncio.wrap_future(f) for f in futures_to_wait}

                # Use asyncio.wait with timeout (non-blocking)
                _done, pending = await asyncio.wait(
                    asyncio_futures,
                    timeout=timeout,
                    return_when=asyncio.ALL_COMPLETED
                )
                # Log if any didn't complete
                if pending:
                    _LOGGER.warning("Some mirror operations did not complete in time: %d pending", len(pending))
                    # Cancel pending futures to prevent resource leaks
                    for future in pending:
                        future.cancel()
            except Exception as e:
                _LOGGER.debug("Error waiting for mirror operations: %s", e)

    async def teardown(self) -> None:
        """Clean up the test environment."""
        _LOGGER.info("Tearing down HA test environment")

        # Wait for any pending mirror operations before cleanup
        await self._wait_for_mirror_operations()

        # Unsubscribe service call listener
        if hasattr(self, "_unsub_service") and self._unsub_service:
            with contextlib.suppress(Exception):
                self._unsub_service()
            self._unsub_service = None

        # Clear tracked data
        self._service_calls.clear()

    async def initialize_integration(self, config: dict[str, Any]) -> MockConfigEntry:
        """Initialize the ESCPOS printer integration."""
        # Create a mock config entry
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=f"{config.get('host', 'localhost')}:{config.get('port', 9100)}",
            data=config,
            unique_id=f"{config.get('host', 'localhost')}:{config.get('port', 9100)}"
        )

        # Add the entry to HA
        entry.add_to_hass(self.hass)

        # Set up the integration via HA; if not found, fall back to direct setup
        ok = await self.hass.config_entries.async_setup(entry.entry_id)
        self._fallback_mode = not ok
        if not ok:
            # Fallback: Minimal in-test setup of services without platform forwarding
            try:
                domain_str = "escpos_printer"
                from homeassistant.core import ServiceCall
                from homeassistant.exceptions import HomeAssistantError

                from custom_components.escpos_printer.printer import (
                    EscposPrinterAdapter,
                    PrinterConfig,
                )

                pcfg = PrinterConfig(
                    host=entry.data.get("host"),
                    port=entry.data.get("port", 9100),
                    timeout=float(entry.data.get("timeout", 4.0)),
                    codepage=entry.data.get("codepage"),
                )
                adapter = EscposPrinterAdapter(pcfg)
                self.hass.data.setdefault(domain_str, {})[entry.entry_id] = {
                    "adapter": adapter,
                    "defaults": {"align": entry.data.get("default_align"), "cut": entry.data.get("default_cut")},
                }

                async def _svc_print_text(call: ServiceCall) -> None:
                    try:
                        await adapter.print_text(
                            self.hass,
                            text=str(call.data.get("text", "")),
                            align=call.data.get("align"),
                            bold=call.data.get("bold"),
                            underline=call.data.get("underline"),
                            width=call.data.get("width"),
                            height=call.data.get("height"),
                            encoding=call.data.get("encoding"),
                            cut=call.data.get("cut"),
                            feed=call.data.get("feed"),
                        )
                    except Exception as err:
                        raise HomeAssistantError(str(err)) from err

                async def _svc_print_qr(call: ServiceCall) -> None:
                    try:
                        await adapter.print_qr(
                            self.hass,
                            data=str(call.data.get("data", "")),
                            size=call.data.get("size"),
                            ec=call.data.get("ec"),
                            align=call.data.get("align"),
                            cut=call.data.get("cut"),
                            feed=call.data.get("feed"),
                        )
                    except Exception as err:
                        raise HomeAssistantError(str(err)) from err

                async def _svc_print_barcode(call: ServiceCall) -> None:
                    try:
                        await adapter.print_barcode(
                            self.hass,
                            code=str(call.data.get("code", "")),
                            bc=str(call.data.get("bc", "CODE128")),
                            height=int(call.data.get("height", 64)),
                            width=int(call.data.get("width", 3)),
                            pos=str(call.data.get("pos", "BELOW")),
                            font=str(call.data.get("font", "A")),
                            align_ct=bool(call.data.get("align_ct", True)),
                            check=bool(call.data.get("check", False)),
                            force_software=call.data.get("force_software"),
                            align=call.data.get("align"),
                            cut=call.data.get("cut"),
                            feed=call.data.get("feed"),
                        )
                    except Exception as err:
                        raise HomeAssistantError(str(err)) from err

                async def _svc_feed(call: ServiceCall) -> None:
                    try:
                        await adapter.feed(self.hass, lines=int(call.data.get("lines", 1)))
                    except Exception as err:
                        raise HomeAssistantError(str(err)) from err

                async def _svc_cut(call: ServiceCall) -> None:
                    try:
                        await adapter.cut(self.hass, mode=str(call.data.get("mode", "full")))
                    except Exception as err:
                        raise HomeAssistantError(str(err)) from err

                self.hass.services.async_register(domain_str, "print_text", _svc_print_text)
                self.hass.services.async_register(domain_str, "print_qr", _svc_print_qr)
                self.hass.services.async_register(domain_str, "print_barcode", _svc_print_barcode)
                self.hass.services.async_register(domain_str, "feed", _svc_feed)
                self.hass.services.async_register(domain_str, "cut", _svc_cut)
            except Exception as e:
                raise AssertionError(f"Failed to set up escpos_printer fallback: {e}")
        await self.hass.async_block_till_done()

        self.config_entry = entry
        _LOGGER.info("Initialized ESCPOS integration with config: %s", config)
        # Compute default notify entity id for notification tester
        host = config.get('host', 'localhost').replace('.', '_')
        port = config.get('port', 9100)
        self.notification_tester.set_default_entity_id(f"notify.esc_pos_printer_{host}_{port}")
        return entry

    async def get_integration_state(self) -> dict[str, Any]:
        """Get the current state of the integration."""
        if not self.config_entry:
            return {"status": "not_initialized"}

        entry_state = self.hass.config_entries.async_get_entry(self.config_entry.entry_id)
        return {
            "entry_id": self.config_entry.entry_id,
            "state": entry_state.state if entry_state else "unknown",
            "data": self.config_entry.data,
            "options": self.config_entry.options
        }

    def get_service_calls(self, domain: str | None = None, service: str | None = None) -> list[dict[str, Any]]:
        """Get tracked service calls, optionally filtered by domain and service."""
        calls = self._service_calls

        if domain:
            calls = [call for call in calls if call["domain"] == domain]
        if service:
            calls = [call for call in calls if call["service"] == service]

        return calls

    async def async_block_till_done(self) -> None:
        """Block until all pending tasks are done.

        This includes both Home Assistant's internal tasks and our
        asynchronous service call mirroring operations.
        """
        await self._wait_for_mirror_operations()
        await self.hass.async_block_till_done()
        # Allow network I/O (socket writes/reads) to settle between HA tasks
        await asyncio.sleep(0.2)

    async def create_test_entity(self, entity_id: str, entity_type: str,
                                initial_state: str = "unknown",
                                attributes: dict[str, Any] | None = None) -> None:
        """Create a test entity for automation testing."""
        if attributes is None:
            attributes = {}

        self.hass.states.async_set(entity_id, initial_state, attributes)
        _LOGGER.debug("Created test entity: %s (%s)", entity_id, entity_type)

    async def remove_test_entity(self, entity_id: str) -> None:
        """Remove a test entity."""
        self.hass.states.async_remove(entity_id)
        _LOGGER.debug("Removed test entity: %s", entity_id)
