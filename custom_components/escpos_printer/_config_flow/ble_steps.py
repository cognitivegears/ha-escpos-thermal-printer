"""Configure BLE printers through Home Assistant's shared scanner."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
import probatio as vol

from ..capabilities.ble_profiles import (
    CRAFTSCO_4777_DIALECT,
    BlePrinterProfile,
    craftsco_4777_variant,
    get_ble_profiles,
    is_craftsco_4777_name,
)
from ..const import (
    CONF_BLE_PROFILE,
    CONF_BT_MAC,
    CONF_CODEPAGE,
    CONF_CONNECTION_TYPE,
    CONF_DEFAULT_CUT,
    CONF_DETECTED_MODEL,
    CONF_LINE_WIDTH,
    CONF_TIMEOUT,
    CONNECTION_TYPE_BLUETOOTH,
)
from ..printer.ble_transport import (
    BLE_ERRORS,
    BLE_PRINTER_SERVICES,
    BlePrinterMismatchError,
    bluetooth_api,
    open_ble_printer,
)
from .bluetooth_helpers import _generate_bt_unique_id, _normalize_bt_mac

_REFRESH = "__refresh__"
_BLE_TIMEOUT = 12.0


class BleFlowMixin:
    """Discover nearby BLE printers and verify the selected model."""

    hass: Any

    async def async_step_reconfigure_bluetooth_le(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a new BLE profile for the current address."""
        return await self.async_step_bluetooth_le(user_input)

    async def async_step_bluetooth_le(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer discovered devices or a manually entered Bluetooth address."""
        profiles = await self.hass.async_add_executor_job(get_ble_profiles)
        errors: dict[str, str] = {}
        if user_input is not None and user_input[CONF_BT_MAC] != _REFRESH:
            result = await self._save_ble_printer(user_input, profiles, errors)
            if result is not None:
                return result

        reconfigure = self.source == "reconfigure"  # type: ignore[attr-defined]
        defaults = self._get_reconfigure_entry().data if reconfigure else {}  # type: ignore[attr-defined]
        current = dict(user_input or defaults)
        if user_input is None and reconfigure and (bluetooth := bluetooth_api(self.hass)):
            info = bluetooth.async_last_service_info(
                self.hass, current[CONF_BT_MAC], connectable=True
            )
            if info and is_craftsco_4777_name(info.name) and CRAFTSCO_4777_DIALECT in profiles:
                current[CONF_BLE_PROFILE] = CRAFTSCO_4777_DIALECT
        if current.get(CONF_BT_MAC) == _REFRESH:
            current.pop(CONF_BT_MAC)
        return self.async_show_form(  # type: ignore[attr-defined,no-any-return]
            step_id="reconfigure_bluetooth_le" if reconfigure else "bluetooth_le",
            data_schema=self.add_suggested_values_to_schema(  # type: ignore[attr-defined]
                vol.Schema(
                    {
                        vol.Required(CONF_BLE_PROFILE): SelectSelector(
                            SelectSelectorConfig(
                                options=[
                                    SelectOptionDict(value=key, label=profile.name)
                                    for key, profile in profiles.items()
                                ],
                                mode=SelectSelectorMode.DROPDOWN,
                            )
                        ),
                        vol.Required(CONF_BT_MAC): SelectSelector(
                            SelectSelectorConfig(
                                options=self._ble_choices(profiles),
                                mode=SelectSelectorMode.DROPDOWN,
                                custom_value=True,
                                sort=False,
                            )
                        ),
                    }
                ),
                current,
            ),
            errors=errors,
        )

    def _ble_choices(self, profiles: dict[str, BlePrinterProfile]) -> list[SelectOptionDict]:
        """Show likely printers first while keeping unnamed devices selectable."""
        choices: list[SelectOptionDict] = []
        if bluetooth := bluetooth_api(self.hass):
            devices = sorted(
                bluetooth.async_discovered_service_info(self.hass, connectable=True),
                key=lambda info: (
                    not any(p.matches_advertisement(info.name) for p in profiles.values()),
                    BLE_PRINTER_SERVICES.isdisjoint(uuid.lower() for uuid in info.service_uuids),
                    info.name.casefold(),
                    info.address,
                ),
            )
            choices.extend(
                SelectOptionDict(value=info.address, label=f"{info.name} ({info.address})")
                for info in devices
            )
        choices.append(SelectOptionDict(value=_REFRESH, label="Refresh list"))
        return choices

    async def _save_ble_printer(
        self,
        user_input: dict[str, Any],
        profiles: dict[str, BlePrinterProfile],
        errors: dict[str, str],
    ) -> ConfigFlowResult | None:
        mac = _normalize_bt_mac(user_input.get(CONF_BT_MAC))
        if mac is None:
            errors[CONF_BT_MAC] = "invalid_bt_mac"
            return None
        profile_key = user_input[CONF_BLE_PROFILE]
        profile = profiles[profile_key]
        reconfigure = self.source == "reconfigure"  # type: ignore[attr-defined]
        entry = self._get_reconfigure_entry() if reconfigure else None  # type: ignore[attr-defined]
        unique_id = _generate_bt_unique_id(mac)
        await self.async_set_unique_id(unique_id)  # type: ignore[attr-defined]
        if reconfigure:
            self._abort_if_unique_id_mismatch()  # type: ignore[attr-defined]
        else:
            self._abort_if_unique_id_configured()  # type: ignore[attr-defined]

        timeout = float(entry.options.get(CONF_TIMEOUT, _BLE_TIMEOUT)) if entry else _BLE_TIMEOUT
        if error := await self._probe_ble_model(mac, timeout, profile):
            errors["base"] = error
            return None

        data = {
            CONF_CONNECTION_TYPE: CONNECTION_TYPE_BLUETOOTH,
            CONF_BLE_PROFILE: profile_key,
            CONF_BT_MAC: mac,
            CONF_TIMEOUT: _BLE_TIMEOUT,
            CONF_CODEPAGE: "UTF-8",
            CONF_DEFAULT_CUT: "none",
            CONF_DETECTED_MODEL: profile.name,
            CONF_LINE_WIDTH: profile.width // 12,
        }
        if entry is not None:
            previous = profiles.get(entry.data.get(CONF_BLE_PROFILE, ""))
            title = profile.name if previous and entry.title == previous.name else entry.title
            return self.async_update_reload_and_abort(  # type: ignore[attr-defined,no-any-return]
                entry, data_updates=data, title=title
            )
        return self.async_create_entry(title=profile.name, data=data)  # type: ignore[attr-defined,no-any-return]

    async def _probe_ble_model(
        self, mac: str, timeout: float, profile: BlePrinterProfile
    ) -> str | None:
        """Confirm GATT connectivity and the firmware's printer model."""
        if (bluetooth := bluetooth_api(self.hass)) is None:
            return "ble_not_available"
        if bluetooth.async_ble_device_from_address(self.hass, mac, connectable=True) is None:
            return "ble_not_found"
        try:
            async with open_ble_printer(self.hass, mac, timeout) as link:
                model = await link.read_model()
                name = link.advertised_name
        except BlePrinterMismatchError:
            return "ble_model_mismatch"
        except BLE_ERRORS:
            return "ble_cannot_connect"
        if profile.dialect == CRAFTSCO_4777_DIALECT:
            matches = craftsco_4777_variant(name, model) is not None
        elif is_craftsco_4777_name(name) or is_craftsco_4777_name(model):
            return "ble_use_4777_profile"
        else:
            matches = profile.matches_model(model)
        return None if matches else "ble_model_mismatch"
