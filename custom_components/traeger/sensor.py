"""Sensor platform for Traeger."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import SIGNAL_STRENGTH_DECIBELS, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.util import slugify

from .const import (
    DOMAIN,
    GRILL_MODE_COOL_DOWN,
    GRILL_MODE_CUSTOM_COOK,
    GRILL_MODE_IDLE,
    GRILL_MODE_IGNITING,
    GRILL_MODE_MANUAL_COOK,
    GRILL_MODE_OFFLINE,
    GRILL_MODE_PREHEATING,
    GRILL_MODE_SHUTDOWN,
    GRILL_MODE_SLEEPING,
)
from .coordinator import TraegerCoordinator
from .entity import TraegerBaseEntity
from .monitor import TraegerGrillMonitor

_LOGGER = logging.getLogger(__name__)

MODE_LABELS: dict[int, str] = {
    GRILL_MODE_OFFLINE: "Offline",
    GRILL_MODE_IGNITING: "Igniting",
    GRILL_MODE_PREHEATING: "Preheating",
    GRILL_MODE_MANUAL_COOK: "Manual Cook",
    GRILL_MODE_CUSTOM_COOK: "Custom Cook",
    GRILL_MODE_COOL_DOWN: "Cool Down",
    GRILL_MODE_SHUTDOWN: "Shutdown",
    GRILL_MODE_IDLE: "Idle",
    GRILL_MODE_SLEEPING: "Sleeping",
}
GRILL_STATE_MAPPING = MODE_LABELS.copy()

# --- BLUETOOTH PROBE SENSOR CLASS ---
class TraegerBluetoothProbeSensor(TraegerBaseEntity, SensorEntity):
    """Representation of a Traeger Bluetooth Probe (BT0, BT1, etc)."""

    def __init__(self, client, grill_id, name, channel, coordinator):
        """Initialize the sensor."""
        super().__init__(client, grill_id, name=f"Probe {channel} BT", coordinator=coordinator)
        self.channel = channel
        self._attr_unique_id = f"{grill_id}_bt_probe_{channel}"
        self._attr_name = f"{name} BT Probe {channel}"
        self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_state_class = SensorStateClass.MEASUREMENT

    def _find_probe(self) -> dict | None:
        """Find this probe in the accessory list by Channel ID."""
        status = (self.coordinator.data.get(self.grill_id, {}).get("status") or {})
        for acc in status.get("acc", []):
            # Match by Channel (BT0, BT1) instead of UUID to be safe at startup
            if acc.get("channel") == self.channel:
                return acc
        return None

    @property
    def available(self):
        """Return True if the probe is reported as connected."""
        acc = self._find_probe()
        if not acc:
            return False
        # Check 'con' (Connected) flag. 1 = Connected.
        return acc.get("con", 0) == 1

    @property
    def native_value(self):
        """Return the current temperature."""
        acc = self._find_probe()
        if acc and "btprobe" in acc:
            return acc["btprobe"].get("get_temp")
        return None
    @property
    def extra_state_attributes(self):
        """Return battery and target temps."""
        acc = self._find_probe()
        if acc and "btprobe" in acc:
            details = acc["btprobe"]
            return {
                "target_temp": details.get("set_temp"),
                "battery_level": details.get("batt"),
                "ambient_temp": details.get("ambient_temp"),
                "uuid": acc.get("uuid")
            }
        return {}


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities) -> None:
    """Set up sensor platform."""
    _LOGGER.debug("Setting up sensor monitor")

    data = hass.data[DOMAIN][entry.entry_id]
    client = data["client"]
    coordinator: TraegerCoordinator = data["coordinator"]

    grills = client.get_grills()
    entities: list[SensorEntity] = []

    for grill in grills:
        grill_id = grill["thingName"]
        grill_name = grill.get("friendlyName", grill_id)

        # Probe monitors: temperature and status
        temp_monitor = TraegerGrillMonitor(
            client,
            grill_id,
            async_add_entities,
            TraegerProbeTempSensor,
            coordinator=coordinator,
        )
        await temp_monitor.async_setup()

        status_monitor = TraegerGrillMonitor(
            client,
            grill_id,
            async_add_entities,
            TraegerProbeStatusSensor,
            coordinator=coordinator,
        )
        await status_monitor.async_setup()

        # Maintenance alerts
        entities.extend(
            [
                MaintenanceAlert(
                    coordinator,
                    client,
                    grill_id,
                    "Grill Clean Alert",
                    "grill_clean_countdown",
                    3600,
                ),
                MaintenanceAlert(
                    coordinator,
                    client,
                    grill_id,
                    "Grease Trap Clean Alert",
                    "grease_trap_clean_countdown",
                    5,
                ),
            ]
        )

        # Main sensors
        entities.extend(
            [
                TraegerSensor(coordinator, client, grill_id, "Pellet Level", "pellet_level", "%"),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Ambient Temperature",
                    "ambient",
                    UnitOfTemperature.FAHRENHEIT,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Cook Timer Remaining",
                    "cook_timer_remaining",
                    UnitOfTime.SECONDS,  # numeric seconds
                    device_class=SensorDeviceClass.DURATION,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Cook Timer Remaining Text",
                    "cook_timer_remaining_text",
                    None,  # string, no device_class
                ),
                TraegerSensor(coordinator, client, grill_id, "Grill State", "system_status", None),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Heating State",
                    "heating_state",
                    None,
                ),
                TraegerSensor(coordinator, client, grill_id, "Cook Cycles", "cook_cycles", None),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Wireless RSSI",
                    "rssi",
                    SIGNAL_STRENGTH_DECIBELS,
                    category=EntityCategory.DIAGNOSTIC,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Wireless SSID",
                    "ssid",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Auger Runtime",
                    "auger",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Fan Runtime",
                    "fan",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Hotrod Runtime",
                    "hotrod",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Runtime",
                    "runtime",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Ignition Failures",
                    "ignite_fail",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=True,
                    visible_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Overheat Errors",
                    "overheat",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=True,
                    visible_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Low Temperature Errors",
                    "lowtemp",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=True,
                    visible_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Bad Thermocouple Errors",
                    "bad_thermocouple",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Auger Overcurrent Errors",
                    "auger_ovrcur",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Auger Disconnect Errors",
                    "auger_disco",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Low Ambient Errors",
                    "low_ambient",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Fan Disconnect Errors",
                    "fan_disco",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Igniter Disconnect Errors",
                    "ign_disco",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
                TraegerSensor(
                    coordinator,
                    client,
                    grill_id,
                    "Firmware",
                    "fw_version",
                    None,
                    category=EntityCategory.DIAGNOSTIC,
                    enabled_default=False,
                ),
            ]
        )

        # --- FORCED: Bluetooth Probe Addition ---
        # We add these blindly so they exist immediately in HA.
        # They will pick up data as soon as the grill reports "BT0" or "BT1".
        entities.append(TraegerBluetoothProbeSensor(client, grill_id, grill_name, "BT0", coordinator))
        entities.append(TraegerBluetoothProbeSensor(client, grill_id, grill_name, "BT1", coordinator))
        # ----------------------------------------

    async_add_entities(entities)


class TraegerSensor(TraegerBaseEntity, SensorEntity):
    """Generic Traeger sensor entity."""

    def __init__(
        self,
        coordinator: TraegerCoordinator,
        client: Any,
        grill_id: str,
        name: str,
        key: str,
        unit: str | None,
        category: EntityCategory | None = None,
        enabled_default: bool = True,
        visible_default: bool = True,
        device_class: SensorDeviceClass | str | None = None,
    ):
        super().__init__(client, grill_id, name, coordinator=coordinator)
        self._key = key
        self._attr_unique_id = f"{grill_id}_{key}"
        self.entity_id = f"sensor.{slugify(grill_id)}_{slugify(name)}"
        self._attr_native_unit_of_measurement = unit
        self._attr_entity_category = category
        self._attr_entity_registry_enabled_default = enabled_default
        self._attr_entity_registry_visible_default = visible_default
        self._attr_has_entity_name = True
        self._attr_device_class = device_class

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def grill_state(self) -> dict:
        return self.coordinator.data.get(self.grill_id, {})

    @property
    def available(self) -> bool:
        return self.grill_state.get("status", {}).get("connected", False)

    @property
    def native_value(self):
        state = self.grill_state
        if not state:
            return None
        # Cook timer remaining: numeric seconds for device_class DURATION
        if self._key == "cook_timer_remaining":
            status = state.get("status", {})
            end = status.get("cook_timer_end", 0)
            current_time = status.get("time", 0)
            if end > 0:
                return max(0, int(end - current_time))
            return None
        # Optional: human-readable string version
        if self._key == "cook_timer_remaining_text":
            status = state.get("status", {})
            end = status.get("cook_timer_end", 0)
            current_time = status.get("time", 0)
            seconds = max(0, end - current_time) if end > 0 else None
            return seconds_to_compact(seconds)
        if self._key in ("grill_state", "system_status"):
            system_status = state.get("status", {}).get("system_status")
            if system_status is None:
                return GRILL_STATE_MAPPING.get(GRILL_MODE_IDLE, "Idle")
            try:
                code = int(system_status)
            except (TypeError, ValueError):
                code = system_status
            return GRILL_STATE_MAPPING.get(code, "Unknown")
        if self._key == "heating_state":
            system_status = state.get("status", {}).get("system_status")
            if system_status is None:
                return "Idle"
            try:
                code = int(system_status)
            except (TypeError, ValueError):
                return "Idle"
            active_modes = {
                GRILL_MODE_IGNITING,
                GRILL_MODE_PREHEATING,
                GRILL_MODE_MANUAL_COOK,
                GRILL_MODE_CUSTOM_COOK,
            }
            return "Heating" if code in active_modes else "Idle"
        if self._key == "cook_cycles":
            return state.get("usage", {}).get("cook_cycles")
        if self._key == "fw_version":
            return state.get("settings", {}).get("fw_version")
        if self._key == "rssi":
            return state.get("settings", {}).get("rssi")
        if self._key == "ssid":
            return state.get("settings", {}).get("ssid")
        if self._key in ["auger", "fan", "hotrod", "runtime"]:
            return state.get("usage", {}).get(self._key)
        if self._key in [
            "ignite_fail",
            "overheat",
            "lowtemp",
            "bad_thermocouple",
            "auger_ovrcur",
            "auger_disco",
            "low_ambient",
            "fan_disco",
            "ign_disco",
        ]:
            return state.get("usage", {}).get("error_stats", {}).get(self._key)
        if self._key in ["grill_clean_countdown", "grease_trap_clean_countdown"]:
            return state.get("usage", {}).get(self._key)
        return state.get("status", {}).get(self._key)


class MaintenanceAlert(TraegerBaseEntity, SensorEntity):
    """Sensor for maintenance alerts (e.g., clean countdowns)."""

    def __init__(
        self,
        coordinator: TraegerCoordinator,
        client: Any,
        grill_id: str,
        name: str,
        key: str,
        threshold: int,
    ):
        super().__init__(client, grill_id, name, coordinator=coordinator)
        self._key = key
        self._threshold = threshold
        self._attr_unique_id = f"{grill_id}_{key}"
        self.entity_id = f"sensor.{slugify(grill_id)}_{slugify(name)}"
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_has_entity_name = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        state = self.coordinator.data.get(self.grill_id, {})
        return state.get("status", {}).get("connected", False)

    @property
    def native_value(self):
        state = self.coordinator.data.get(self.grill_id, {})
        usage = state.get("usage") or {}
        value = usage.get(self._key)
        if value is None:
            return None
        return value <= self._threshold


class TraegerProbeSensor(TraegerBaseEntity, SensorEntity):
    """Sensor for probe channel."""

    def __init__(self, client: Any, grill_id: str, channel: str, *, coordinator=None) -> None:
        super().__init__(client, grill_id, name=f"Probe {channel}", coordinator=coordinator)
        self._channel = channel
        self._attr_unique_id = f"{grill_id}_probe_sensor_{channel}"
        self.entity_id = f"sensor.{slugify(grill_id)}_probe_{slugify(channel)}"
        self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
        self._attr_entity_registry_visible_default = False
        self._attr_has_entity_name = True

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        state = self.grill_state or {}
        status = state.get("status") or {}
        for acc in status.get("acc", []):
            if (acc.get("uuid") == self._channel) or (acc.get("channel") == self._channel):
                return acc.get("con", 0) == 1
        return False

    @property
    def native_value(self) -> float | None:
        state = self.grill_state or {}
        status = state.get("status") or {}
        for acc in status.get("acc", []):
            if (acc.get("uuid") == self._channel) or (acc.get("channel") == self._channel):
                temp = (acc.get("probe") or {}).get("get_temp")
                return float(temp) if temp is not None else None
        return None

    @property
    def native_unit_of_measurement(self):
        return self.grill_units


class TraegerProbeTempSensor(TraegerBaseEntity, SensorEntity):
    """Probe temperature."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE  # ensure device class

    def __init__(self, client: Any, grill_id: str, channel: str, coordinator=None):
        super().__init__(client, grill_id, name=f"Probe {channel}", coordinator=coordinator)
        self.channel = channel
        self._attr_unique_id = f"{grill_id}_probe_{channel}"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    @property
    def native_unit_of_measurement(self) -> str:
        """Return the temperature unit."""
        # Traeger client already maps units flag to HA constants
        # Fallback to Fahrenheit to avoid None
        return self.client.get_units_for_device(self.grill_id) or UnitOfTemperature.FAHRENHEIT

    @property
    def native_value(self):
        status = (self.grill_state or {}).get("status") or {}
        for acc in status.get("acc", []):
            if (
                acc.get("type") == "probe"
                and (acc.get("uuid") or acc.get("channel")) == self.channel
            ):
                return (acc.get("probe") or {}).get("get_temp")
        return None

    @property
    def available(self) -> bool:
        status = (self.grill_state or {}).get("status") or {}
        return bool(status.get("connected", False))


class TraegerProbeStatusSensor(TraegerBaseEntity, SensorEntity):
    """Text status for a probe channel: idle/set/close/at_temp/fell_out."""

    _attr_icon = "mdi:thermometer"

    def __init__(self, client, grill_id: str, channel: str, *, coordinator=None) -> None:
        super().__init__(client, grill_id, name=f"Probe {channel} status", coordinator=coordinator)
        self._channel = channel
        self._attr_unique_id = f"{grill_id}_probe_{channel}_status"
        self.entity_id = f"sensor.{slugify(grill_id)}_probe_{slugify(channel)}_status"
        self._attr_entity_registry_visible_default = True
        self._attr_has_entity_name = True
        # Internal state tracking for alarm logic
        self.previous_target_temp: float | int | None = None
        self.probe_alarm: bool = False

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self.coordinator:
            self.async_on_remove(self.coordinator.async_add_listener(self.async_write_ha_state))

    def _find_probe_accessory(self) -> dict | None:
        """Return the accessory dict for this probe channel using coordinator snapshot."""
        status = (self.grill_state or {}).get("status") or {}
        for acc in status.get("acc", []):
            if acc.get("type") != "probe":
                continue
            chan = acc.get("uuid") or acc.get("channel")
            if chan == self._channel:
                return acc
        return None

    @property
    def native_unit_of_measurement(self) -> None:
        """No unit; textual state."""
        return None

    @property
    def native_value(self) -> str | None:
        """Compute textual probe status using legacy rules."""
        acc = self._find_probe_accessory()
        if acc is None or "probe" not in acc:
            return "idle"

        probe = acc["probe"] or {}
        target_temp = probe.get("set_temp", 0) or 0
        probe_temp = probe.get("get_temp")
        try:
            probe_temp = float(probe_temp) if probe_temp is not None else None
        except (TypeError, ValueError):
            probe_temp = None

        # Grill mode for alarm gating
        state = self.client.get_state_for_device(self.grill_id) or {}
        status = state.get("status") or {}
        grill_mode = status.get("system_status")

        # Active modes (kept aligned with your constants)
        active_modes = {
            GRILL_MODE_PREHEATING,
            GRILL_MODE_MANUAL_COOK,
            GRILL_MODE_CUSTOM_COOK,
            GRILL_MODE_IGNITING,
        }

        # Alarm tracking (same semantics as your legacy code)
        if probe.get("alarm_fired"):
            self.probe_alarm = True
        else:
            target_changed = target_temp != self.previous_target_temp
            if (target_changed and target_temp != 0) or grill_mode not in active_modes:
                self.probe_alarm = False

        # Fell-out threshold
        fell_out_temp = 102 if self.grill_units == UnitOfTemperature.CELSIUS else 215

        if probe_temp is None:
            state_str = "idle"
        elif probe_temp >= fell_out_temp:
            state_str = "fell_out"
        elif self.probe_alarm:
            state_str = "at_temp"
        elif target_temp != 0 and grill_mode in active_modes:
            close_delta = 3 if self.grill_units == UnitOfTemperature.CELSIUS else 5
            state_str = "close" if (probe_temp + close_delta) >= target_temp else "set"
        else:
            self.probe_alarm = False
            state_str = "idle"

        self.previous_target_temp = target_temp
        return state_str

    @property
    def extra_state_attributes(self) -> dict:
        """Expose helpful details."""
        acc = self._find_probe_accessory()
        probe = (acc or {}).get("probe") or {}
        return {
            "channel": self._channel,
            "target_temp": probe.get("set_temp"),
            "current_temp": probe.get("get_temp"),
            "alarm_fired": probe.get("alarm_fired"),
        }


def seconds_to_compact(seconds: float | None) -> str | None:
    """Return 'H:MM:SS' or 'M:SS' (e.g., 310 -> '5:10', 3750 -> '1:02:30')."""
    if seconds is None:
        return None
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
