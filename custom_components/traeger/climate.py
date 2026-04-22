"""Climate platform for Traeger."""
from __future__ import annotations

import logging

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    #    GRILL_MODE_IDLE,
    #    GRILL_MODE_SLEEPING,
    #    GRILL_MODE_SHUTDOWN,
    GRILL_MIN_TEMP_C,
    GRILL_MIN_TEMP_F,
    #   GRILL_MODE_COOL_DOWN,
    GRILL_MODE_CUSTOM_COOK,
    GRILL_MODE_IGNITING,
    GRILL_MODE_MANUAL_COOK,
    GRILL_MODE_OFFLINE,
    GRILL_MODE_PREHEATING,
    PROBE_PRESET_MODES,
)
from .coordinator import TraegerCoordinator
from .entity import TraegerBaseEntity
from .monitor import TraegerGrillMonitor

_LOGGER = logging.getLogger(__name__)


def _dedupe_entities(entities: list) -> list:
    """Avoid adding the same entity twice."""
    seen_ids: set[str] = set()
    out: list = []
    for ent in entities:
        eid = getattr(ent, "entity_id", None)
        if eid and eid in seen_ids:
            continue
        if eid:
            seen_ids.add(eid)
        out.append(ent)
    return out


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up Traeger climate entities from a config entry."""
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator: TraegerCoordinator = data.get("coordinator")

    grills = client.get_grills()
    entities: list[ClimateEntity] = []

    added_grills: set[str] = data.setdefault("climate_added_grills", set())
    added_probe_monitors: set[str] = data.setdefault("climate_added_probe_monitors", set())

    for grill in grills:
        grill_id = grill["thingName"]

        # Add the main grill climate entity once
        if grill_id not in added_grills:
            # FIX: correct constructor order/signature
            entities.append(TraegerGrill(client, grill_id, coordinator=coordinator))
            added_grills.add(grill_id)

        if grill_id not in added_probe_monitors:
            climate_monitor = TraegerGrillMonitor(
                client,
                grill_id,
                async_add_entities,
                TraegerGrillProbe,
                coordinator=coordinator,
            )
            await climate_monitor.async_setup()
            added_probe_monitors.add(grill_id)

    if entities:
        async_add_entities(_dedupe_entities(entities))


class TraegerGrill(ClimateEntity, TraegerBaseEntity):
    """Main grill climate entity."""

    def __init__(self, client, grill_id: str, *, coordinator=None) -> None:
        super().__init__(client, grill_id, name="Grill Climate", coordinator=coordinator)
        self._attr_unique_id = f"{grill_id}_climate"
        self.entity_id = f"climate.{slugify(grill_id)}_climate"
        self._attr_entity_registry_visible_default = True
        _LOGGER.debug(f"Initialized climate {self.entity_id} for grill {grill_id}")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def available(self):
        state = self.grill_state or {}
        return state.get("status", {}).get("connected", False)

    @property
    def icon(self):
        return "mdi:grill"

    @property
    def temperature_unit(self):
        return self.grill_units or UnitOfTemperature.FAHRENHEIT

    @property
    def hvac_mode(self):
        state = self.grill_state or {}
        status = state.get("status", {})
        system_status = status.get("system_status", GRILL_MODE_OFFLINE)
        if system_status in [
            GRILL_MODE_PREHEATING,
            GRILL_MODE_IGNITING,
            GRILL_MODE_MANUAL_COOK,
            GRILL_MODE_CUSTOM_COOK,
        ]:
            return HVACMode.HEAT
        return HVACMode.OFF

    @property
    def hvac_modes(self):
        return [HVACMode.HEAT, HVACMode.OFF]

    @property
    def current_temperature(self):
        state = self.grill_state or {}
        status = state.get("status", {})
        return status.get("grill")

    @property
    def target_temperature(self):
        state = self.grill_state or {}
        status = state.get("status", {})
        return status.get("set")

    @property
    def min_temp(self):
        units = self.temperature_unit
        limits = self.grill_limits or {}
        if not limits:
            return GRILL_MIN_TEMP_C if units == UnitOfTemperature.CELSIUS else GRILL_MIN_TEMP_F
        return limits.get(
            "min_grill_temp",
            GRILL_MIN_TEMP_C if units == UnitOfTemperature.CELSIUS else GRILL_MIN_TEMP_F,
        )

    @property
    def max_temp(self):
        units = self.temperature_unit
        limits = self.grill_limits or {}
        if not limits:
            return GRILL_MIN_TEMP_C if units == UnitOfTemperature.CELSIUS else GRILL_MIN_TEMP_F
        return limits.get(
            "max_grill_temp",
            GRILL_MIN_TEMP_C if units == UnitOfTemperature.CELSIUS else GRILL_MIN_TEMP_F,
        )

    @property
    def grill_limits(self) -> dict | None:
        state = self.grill_state or {}
        return state.get("limits")

    async def async_set_hvac_mode(self, hvac_mode):
        if hvac_mode == HVACMode.HEAT:
            await self.client.set_switch(self.grill_id, 10)
        else:
            await self.client.shutdown_grill(self.grill_id)
        if hasattr(self.client, "trigger_mqtt_refresh"):
            _LOGGER.debug(f"Requesting MQTT poke after hvac_mode change for {self.entity_id}")
            await self.client.trigger_mqtt_refresh(self.grill_id)
        self.async_schedule_update_ha_state()

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self.client.set_temperature(self.grill_id, int(temperature))
            if hasattr(self.client, "trigger_mqtt_refresh"):
                _LOGGER.debug(f"Requesting MQTT poke after target temp change for {self.entity_id}")
                await self.client.trigger_mqtt_refresh(self.grill_id)
            self.async_schedule_update_ha_state()

    @property
    def supported_features(self):
        return ClimateEntityFeature.TARGET_TEMPERATURE


class TraegerGrillProbe(ClimateEntity, TraegerBaseEntity):
    """Climate entity for a grill probe."""

    def __init__(self, client, grill_id: str, channel: str, *, coordinator=None) -> None:
        super().__init__(client, grill_id, name=f"Probe {channel}", coordinator=coordinator)
        self._channel = channel
        self.accessory_id = channel
        self._attr_unique_id = f"{grill_id}_probe_{channel}"
        self.entity_id = f"climate.{slugify(grill_id)}_probe_{slugify(channel)}"
        self._attr_entity_registry_visible_default = True
        _LOGGER.debug(f"Initialized probe {self.entity_id} for grill {grill_id}")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def available(self):
        state = self.grill_state or {}
        status = state.get("status") or {}
        for acc in status.get("acc", []):
            if (acc.get("uuid") == self._channel) or (acc.get("channel") == self._channel):
                return acc.get("con", 0) == 1
        return False

    @property
    def icon(self):
        return "mdi:thermometer"

    @property
    def temperature_unit(self):
        return self.grill_units or UnitOfTemperature.FAHRENHEIT

    @property
    def hvac_mode(self):
        if not self.grill_state or not self.available:
            return HVACMode.OFF
        return HVACMode.HEAT

    @property
    def hvac_modes(self):
        return [HVACMode.HEAT]

    @property
    def preset_mode(self):
        if not self.grill_state or not self.available:
            return None
        probe_temp = self.target_temperature
        for preset, temps in PROBE_PRESET_MODES.items():
            if temps[self.temperature_unit] == probe_temp:
                return preset
        return None

    @property
    def preset_modes(self):
        return list(PROBE_PRESET_MODES.keys())

    @property
    def current_temperature(self):
        state = self.grill_state or {}
        status = state.get("status") or {}
        for acc in status.get("acc", []):
            if (acc.get("uuid") == self._channel) or (acc.get("channel") == self._channel):
                return (acc.get("probe") or {}).get("get_temp")
        return None

    @property
    def target_temperature(self):
        state = self.grill_state or {}
        status = state.get("status") or {}
        for acc in status.get("acc", []):
            if (acc.get("uuid") == self._channel) or (acc.get("channel") == self._channel):
                return (acc.get("probe") or {}).get("set_temp")
        return None

    @property
    def min_temp(self):
        return 0

    @property
    def max_temp(self):
        return 100 if self.temperature_unit == UnitOfTemperature.CELSIUS else 212

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature")
        if temperature is not None:
            await self.client.set_probe_temperature(self.grill_id, int(temperature))
            self.async_schedule_update_ha_state()

    async def async_set_preset_mode(self, preset_mode):
        if preset_mode in PROBE_PRESET_MODES:
            await self.client.set_probe_temperature(
                self.grill_id, PROBE_PRESET_MODES[preset_mode][self.temperature_unit]
            )
            self.async_schedule_update_ha_state()

    @property
    def supported_features(self):
        return ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE