"""Tests for Traeger pellet level capability behavior."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


SENSOR_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "traeger" / "sensor.py"


def _load_traeger_sensor_class():
    """Load TraegerSensor with minimal module stubs for unit testing."""

    # Stub Home Assistant modules used by sensor.py.
    ha = types.ModuleType("homeassistant")
    sys.modules["homeassistant"] = ha

    components = types.ModuleType("homeassistant.components")
    sys.modules["homeassistant.components"] = components
    sensor_module = types.ModuleType("homeassistant.components.sensor")

    class SensorEntity:
        pass

    class SensorDeviceClass:
        DURATION = "duration"
        TEMPERATURE = "temperature"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    sensor_module.SensorEntity = SensorEntity
    sensor_module.SensorDeviceClass = SensorDeviceClass
    sensor_module.SensorStateClass = SensorStateClass
    sys.modules["homeassistant.components.sensor"] = sensor_module

    config_entries = types.ModuleType("homeassistant.config_entries")
    config_entries.ConfigEntry = object
    sys.modules["homeassistant.config_entries"] = config_entries

    const = types.ModuleType("homeassistant.const")
    const.SIGNAL_STRENGTH_DECIBELS = "dBm"

    class UnitOfTemperature:
        FAHRENHEIT = "°F"

    class UnitOfTime:
        SECONDS = "s"

    const.UnitOfTemperature = UnitOfTemperature
    const.UnitOfTime = UnitOfTime
    sys.modules["homeassistant.const"] = const

    core = types.ModuleType("homeassistant.core")
    core.HomeAssistant = object
    sys.modules["homeassistant.core"] = core

    helpers_entity = types.ModuleType("homeassistant.helpers.entity")

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    helpers_entity.EntityCategory = EntityCategory
    sys.modules["homeassistant.helpers.entity"] = helpers_entity

    util = types.ModuleType("homeassistant.util")
    util.slugify = lambda value: str(value).lower().replace(" ", "_")
    sys.modules["homeassistant.util"] = util

    # Stub package and local modules used by relative imports.
    custom_components = types.ModuleType("custom_components")
    custom_components.__path__ = []
    sys.modules["custom_components"] = custom_components

    traeger_pkg = types.ModuleType("custom_components.traeger")
    traeger_pkg.__path__ = []
    sys.modules["custom_components.traeger"] = traeger_pkg

    local_const = types.ModuleType("custom_components.traeger.const")
    local_const.DOMAIN = "traeger"
    local_const.GRILL_MODE_COOL_DOWN = 1
    local_const.GRILL_MODE_CUSTOM_COOK = 2
    local_const.GRILL_MODE_IDLE = 3
    local_const.GRILL_MODE_IGNITING = 4
    local_const.GRILL_MODE_MANUAL_COOK = 5
    local_const.GRILL_MODE_OFFLINE = 6
    local_const.GRILL_MODE_PREHEATING = 7
    local_const.GRILL_MODE_SHUTDOWN = 8
    local_const.GRILL_MODE_SLEEPING = 9
    sys.modules["custom_components.traeger.const"] = local_const

    local_coordinator = types.ModuleType("custom_components.traeger.coordinator")

    class TraegerCoordinator:
        pass

    local_coordinator.TraegerCoordinator = TraegerCoordinator
    sys.modules["custom_components.traeger.coordinator"] = local_coordinator

    local_entity = types.ModuleType("custom_components.traeger.entity")

    class TraegerBaseEntity:
        def __init__(self, client, grill_id, name=None, *, coordinator=None):
            self.client = client
            self.grill_id = grill_id
            self.coordinator = coordinator
            self._attr_name = name

    local_entity.TraegerBaseEntity = TraegerBaseEntity
    sys.modules["custom_components.traeger.entity"] = local_entity

    local_monitor = types.ModuleType("custom_components.traeger.monitor")

    class TraegerGrillMonitor:
        pass

    local_monitor.TraegerGrillMonitor = TraegerGrillMonitor
    sys.modules["custom_components.traeger.monitor"] = local_monitor

    # Ensure a fresh module import each time.
    sys.modules.pop("custom_components.traeger.sensor", None)

    spec = importlib.util.spec_from_file_location("custom_components.traeger.sensor", SENSOR_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["custom_components.traeger.sensor"] = module
    spec.loader.exec_module(module)
    return module.TraegerSensor


class _DummyCoordinator:
    def __init__(self, state):
        self.data = {"grill-1": state}


class _DummyClient:
    pass


def _make_pellet_sensor(state: dict):
    sensor_cls = _load_traeger_sensor_class()
    return sensor_cls(
        _DummyCoordinator(state),
        _DummyClient(),
        "grill-1",
        "Pellet Level",
        "pellet_level",
        "%",
    )


def test_pellet_level_unavailable_without_pellet_sensor():
    sensor = _make_pellet_sensor(
        {
            "status": {"connected": True, "pellet_level": 40},
            "features": {"pellet_sensor_connected": 0},
        }
    )

    assert sensor.available is False
    assert sensor.native_value is None


def test_pellet_level_reports_value_when_sensor_connected():
    sensor = _make_pellet_sensor(
        {
            "status": {"connected": True, "pellet_level": 62},
            "features": {"pellet_sensor_connected": 1},
        }
    )

    assert sensor.available is True
    assert sensor.native_value == 62


def test_pellet_level_unavailable_when_grill_disconnected():
    sensor = _make_pellet_sensor(
        {
            "status": {"connected": False, "pellet_level": 70},
            "features": {"pellet_sensor_connected": 1},
        }
    )

    assert sensor.available is False
