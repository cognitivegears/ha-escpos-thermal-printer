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
from homeassistant.helpers.service_info.dhcp import DhcpServiceInfo

from ..const import DEFAULT_PORT, DEFAULT_TIMEOUT
from .network_helpers import _can_connect, query_printer_id

_LOGGER = logging.getLogger(__name__)


class DiscoveryFlowMixin:
    """Mixin providing the DHCP discovery entry point.

    Expects from the composed flow class:
    - hass, async_set_unique_id(), _abort_if_unique_id_configured(),
      async_abort(), async_step_network()
    - _detected: dict[str, str] (main_flow.__init__)
    - _discovery_host: str | None (main_flow.__init__)
    """

    hass: Any
    _detected: dict[str, str]
    _discovery_host: str | None

    async def async_step_dhcp(self, discovery_info: DhcpServiceInfo) -> ConfigFlowResult:
        """Handle a DHCP-discovered printer candidate."""
        host = discovery_info.ip
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

        self._detected = (
            await self.hass.async_add_executor_job(
                query_printer_id, host, DEFAULT_PORT, DEFAULT_TIMEOUT
            )
            or {}
        )
        self._discovery_host = host
        name = self._detected.get("model") or discovery_info.hostname
        self.context["title_placeholders"] = {"name": f"{name} ({host})"}  # type: ignore[attr-defined]
        return await self.async_step_network()  # type: ignore[attr-defined,no-any-return]
