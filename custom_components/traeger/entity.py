# Revision: 2025-08-20
"""Base entity for Traeger."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.const import UnitOfTemperature
from homeassistant.core import callback
import homeassistant.helpers.device_registry as dr
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class TraegerBaseEntity(CoordinatorEntity, RestoreEntity):
    """Base entity for Traeger with dynamic device info."""

    _attr_has_entity_name = True

    def __init__(
        self,
        client: Any,
        grill_id: str,
        name: str | None = None,
        *,
        coordinator: CoordinatorEntity | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.client = client
        self.grill_id = grill_id
        self._attr_name = name
        self._last_dev_info: tuple | None = None
        # Do not construct DeviceInfo here; device_info is provided dynamically

    def _get_fw_version(self) -> str | None:
        """Return firmware version from latest snapshot."""
        state: dict[str, Any] = (
            self.grill_state or self.client.get_state_for_device(self.grill_id) or {}
        )
        settings = state.get("settings") or {}
        status = state.get("status") or {}
        fw = settings.get("fw_version") or state.get("fw_version") or status.get("fw_version")
        if isinstance(fw, str) and fw.strip():
            return fw.strip()
        return None

    def _get_grill_info(self) -> dict[str, Any]:
        """Lookup grill metadata from the client."""
        try:
            for g in self.client.get_grills():
                if g.get("thingName") == self.grill_id:
                    return g
        except Exception:
            pass
        return {}

    def _compose_device_info(self) -> dict[str, Any]:
        """Build device info dict from grill metadata and firmware."""
        grill = self._get_grill_info()
        model = grill.get("grillModel") or {}
        friendly_name = grill.get("friendlyName") or self.grill_id
        make = model.get("make") or "Traeger"
        model_name = model.get("name")
        model_num = model.get("modelNumber")

        if model_name and model_num:
            model_str = f"{model_name} ({model_num})"
        else:
            model_str = model_name or model_num or "Traeger Grill"

        return {
            "identifiers": {(DOMAIN, self.grill_id)},
            "manufacturer": make,
            "model": model_str,
            "name": friendly_name,
            "sw_version": self._get_fw_version(),
        }

    @property
    def device_info(self) -> dict[str, Any]:
        """Return dynamic device info dict for the registry."""
        return self._compose_device_info()

    def _lookup_device(self, dev_reg: dr.DeviceRegistry):
        """Find this grill's device, preferring the newer registry API when present."""
        identifier = (DOMAIN, self.grill_id)
        by_identifier = getattr(dev_reg, "async_get_device_by_identifier", None)
        config_entry = getattr(self.platform, "config_entry", None) if self.platform else None
        if by_identifier is not None and config_entry is not None:
            # HA 2026.11+: identifiers are only unique per config entry.
            return by_identifier(identifier, config_entry.entry_id)
        return dev_reg.async_get_device(identifiers={identifier})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def _update_device_registry() -> None:
            dev_info = self._compose_device_info()
            # Only touch the registry when name/model/firmware actually changed.
            # Previously every entity spawned a task on every MQTT push.
            key = (
                dev_info.get("name"),
                dev_info.get("manufacturer"),
                dev_info.get("model"),
                dev_info.get("sw_version"),
            )
            if key == self._last_dev_info:
                return
            self._last_dev_info = key
            dev_reg = dr.async_get(self.hass)
            device = self._lookup_device(dev_reg)
            if device is None:
                return

            updates: dict[str, Any] = {}
            name = dev_info.get("name")
            manufacturer = dev_info.get("manufacturer")
            model = dev_info.get("model")
            sw_version = dev_info.get("sw_version")

            if name and device.name != name:
                updates["name"] = name
            if manufacturer and device.manufacturer != manufacturer:
                updates["manufacturer"] = manufacturer
            if model and device.model != model:
                updates["model"] = model
            if sw_version and device.sw_version != sw_version:
                updates["sw_version"] = sw_version

            if updates:
                dev_reg.async_update_device(device.id, **updates)

        # Update now and on future coordinator pushes (synchronously, no task per push)
        _update_device_registry()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(_update_device_registry))

    def _friendly_name_from_state(self) -> str | None:
        details = (self.grill_state or {}).get("details") or {}
        return details.get("friendlyName")

    def _model_from_state(self) -> str | None:
        state = self.grill_state or {}
        details = state.get("details") or {}
        settings = state.get("settings") or {}
        return (
            str(details.get("deviceType"))
            if details.get("deviceType") is not None
            else (str(settings.get("device_type_id")) if settings.get("device_type_id") else None)
        )

    def _fw_from_state(self) -> str | None:
        settings = (self.grill_state or {}).get("settings") or {}
        return settings.get("fw_version")

    @property
    def grill_state(self) -> dict[str, Any] | None:
        """Prefer coordinator snapshot; fallback to client cache."""
        if getattr(self, "coordinator", None) and self.coordinator and self.coordinator.data:
            return self.coordinator.data.get(self.grill_id)
        return self.client.get_state_for_device(self.grill_id)

    @property
    def grill_units(self) -> UnitOfTemperature:
        """Return the device temperature units."""
        return self.client.get_units_for_device(self.grill_id)

    @property
    def available(self) -> bool:
        """Entity is available when we have a snapshot and the grill is connected."""
        state = self.grill_state or {}
        status = state.get("status") or {}
        if status:
            return bool(status.get("connected", False))
        # Fallback if no snapshot yet
        return bool(self.client.get_cloudconnect(self.grill_id))
