"""DHCP discovery step mixin.

Evidence-only hostname matchers live in manifest.json ("tm-*", "rongta_*").
A match is confirmed by a TCP probe of port 9100 before the user ever sees
a discovery card, so matcher false positives abort silently. The existing
network form is the confirmation UI — discovery just prefills it.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.device_registry import format_mac
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from ..const import CONF_MAC_ADDRESS, DEFAULT_PORT, DEFAULT_TIMEOUT, DOMAIN
from .network_helpers import _can_connect, query_printer_id

_LOGGER = logging.getLogger(__name__)


class DiscoveryFlowMixin:
    """Mixin providing the DHCP discovery entry point.

    Expects from the composed flow class:
    - hass, async_set_unique_id(), _abort_if_unique_id_configured(),
      async_abort(), async_step_network()
    - _detected: dict[str, str] (main_flow.__init__)
    - _discovery_host: str | None (main_flow.__init__)
    - _discovery_port: int | None (main_flow.__init__)
    - _discovery_mac: str | None (main_flow.__init__)
    """

    hass: Any
    _detected: dict[str, str]
    _discovery_host: str | None
    _discovery_port: int | None
    _discovery_mac: str | None

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle a DHCP-discovered printer candidate."""
        host = discovery_info.ip
        mac = format_mac(discovery_info.macaddress)
        self._discovery_mac = mac

        # A known MAC at a new IP (DHCP lease change) updates the existing
        # entry in place instead of offering a duplicate -- see "Follow-up:
        # MAC-tracked discovery identity" in the design doc. Only one
        # network entry can plausibly carry a given MAC, so the first match
        # wins; a same-IP match just falls through to the normal
        # already-configured abort below.
        for entry in self.hass.config_entries.async_entries(DOMAIN):
            if entry.data.get(CONF_MAC_ADDRESS) != mac:
                continue
            if str(entry.data.get(CONF_HOST, "")).lower() == host.lower():
                break
            entry_port = entry.data.get(CONF_PORT, DEFAULT_PORT)
            new_unique_id = f"{host.lower()}:{entry_port}"
            colliding = self.hass.config_entries.async_entry_for_domain_unique_id(
                DOMAIN, new_unique_id
            )
            if colliding is not None and colliding.entry_id != entry.entry_id:
                break  # unique_id already owned by a different entry
            self.hass.config_entries.async_update_entry(
                entry, data={**entry.data, CONF_HOST: host}, unique_id=new_unique_id
            )
            self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_abort(reason="already_configured")  # type: ignore[attr-defined,no-any-return]

        await self.async_set_unique_id(f"{host.lower()}:{DEFAULT_PORT}")  # type: ignore[attr-defined]
        self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

        if not await self.hass.async_add_executor_job(
            _can_connect, host, DEFAULT_PORT, DEFAULT_TIMEOUT
        ):
            _LOGGER.debug(
                "DHCP match %s (%s) not listening on %s; ignoring",
                discovery_info.hostname,
                host,
                DEFAULT_PORT,
            )
            return self.async_abort(reason="cannot_connect")  # type: ignore[attr-defined,no-any-return]

        detected = (
            await self.hass.async_add_executor_job(
                query_printer_id, host, DEFAULT_PORT, DEFAULT_TIMEOUT
            )
            or {}
        )

        # "tm-*" also matches Prometheus node_exporter's default port 9100,
        # so a port-probe alone is not brand-exclusive evidence for it -- a
        # positive GS I identification is required before showing a card.
        # "rongta_*" is a brand-exclusive hostname prefix, so the port probe
        # above is sufficient evidence on its own.
        if discovery_info.hostname.lower().startswith("tm-") and not detected:
            _LOGGER.debug(
                "DHCP match %s (%s) did not answer GS I identification; ignoring",
                discovery_info.hostname,
                host,
            )
            return self.async_abort(reason="cannot_connect")  # type: ignore[attr-defined,no-any-return]

        self._detected = detected
        self._discovery_host = host
        self._discovery_port = DEFAULT_PORT
        name = detected.get("model") or discovery_info.hostname
        self.context["title_placeholders"] = {"name": f"{name} ({host})"}  # type: ignore[attr-defined]
        return await self.async_step_network()  # type: ignore[attr-defined,no-any-return]
