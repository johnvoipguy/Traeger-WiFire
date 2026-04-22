"""Number platform for Traeger."""

import logging

from homeassistant.components.number import NumberEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import TraegerCoordinator
from .entity import TraegerBaseEntity

_LOGGER: logging.Logger = logging.getLogger(__package__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Setup number platform."""
    _LOGGER.debug("Setting up number entities")
    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator: TraegerCoordinator | None = data.get("coordinator")
    grills = client.get_grills()
    entities = []
    for grill in grills:
        grill_id = grill["thingName"]
        entities.append(TraegerNumber(client, grill_id, coordinator))
    if entities:
        async_add_entities(entities)


class TraegerNumber(TraegerBaseEntity, NumberEntity):
    def __init__(self, client, grill_id, coordinator=None):
        super().__init__(client, grill_id, name="Cook Timer", coordinator=coordinator)
        self._attr_unique_id = f"{grill_id}_number"
        self.entity_id = f"number.{slugify(grill_id)}_number"
        self._attr_native_min_value = 0
        self._attr_native_max_value = 1440  # 24 hours in minutes
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = "min"
        _LOGGER.debug(f"Initialized number {self.entity_id} for grill {grill_id}")

    @property
    def icon(self):
        return "mdi:timer"

    @property
    def name(self):
        return self._attr_name

    @property
    def unique_id(self):
        return self._attr_unique_id

    @property
    def available(self):
        return (
            self.grill_state.get("status", {}).get("connected", False)
            if self.grill_state
            else False
        )

    async def async_set_native_value(self, value):
        await self.client.set_timer_sec(
            self.grill_id, int(value * 60)
        )  # Convert minutes to seconds
        self.async_schedule_update_ha_state()

    @property
    def native_value(self):
        state = self.client.get_state_for_device(self.grill_id)
        if not state or not state.get("status"):
            _LOGGER.debug(f"No state data for {self.entity_id}: state={state}")
            return None
        start = state.get("status", {}).get("cook_timer_start", 0)
        end = state.get("status", {}).get("cook_timer_end", 0)
        seconds = max(0, end - start) if end > 0 else None
        return seconds / 60 if seconds is not None else None  # Convert seconds to minutes

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))
