"""Tests for temperature unit handling on Celsius and Fahrenheit grills."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_PATH = PROJECT_ROOT / "custom_components" / "traeger"

CELSIUS = "°C"
FAHRENHEIT = "°F"


def _module(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_local(name: str):
    """Load a real module from the integration package."""
    full_name = f"custom_components.traeger.{name}"
    sys.modules.pop(full_name, None)
    spec = importlib.util.spec_from_file_location(full_name, PACKAGE_PATH / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


def _install_stubs() -> None:
    """Stub the Home Assistant modules and sibling modules the platforms import."""

    class UnitOfTemperature:
        CELSIUS = "°C"
        FAHRENHEIT = "°F"

    class UnitOfTime:
        SECONDS = "s"

    class SensorDeviceClass:
        DURATION = "duration"
        TEMPERATURE = "temperature"

    class SensorStateClass:
        MEASUREMENT = "measurement"

    class ClimateEntityFeature:
        TARGET_TEMPERATURE = 1
        PRESET_MODE = 2

    class HVACMode:
        HEAT = "heat"
        OFF = "off"

    class EntityCategory:
        DIAGNOSTIC = "diagnostic"

    class OptionsFlow:
        """Mimic HA >= 2025.12: ``config_entry`` is a getter-only property."""

        @property
        def config_entry(self):
            return getattr(self, "_config_entry", None)

    _module("homeassistant")
    _module("homeassistant.components")
    _module(
        "homeassistant.components.sensor",
        SensorEntity=type("SensorEntity", (), {}),
        SensorDeviceClass=SensorDeviceClass,
        SensorStateClass=SensorStateClass,
    )
    _module(
        "homeassistant.components.climate",
        ClimateEntity=type("ClimateEntity", (), {}),
        ClimateEntityFeature=ClimateEntityFeature,
        HVACMode=HVACMode,
    )
    _module(
        "homeassistant.config_entries",
        ConfigEntry=object,
        OptionsFlow=OptionsFlow,
        ConfigFlow=type("ConfigFlow", (), {"__init_subclass__": classmethod(lambda cls, **kw: None)}),
        CONN_CLASS_CLOUD_POLL="cloud_poll",
    )
    _module(
        "homeassistant.const",
        SIGNAL_STRENGTH_DECIBELS="dBm",
        UnitOfTemperature=UnitOfTemperature,
        UnitOfTime=UnitOfTime,
    )
    _module("homeassistant.core", HomeAssistant=object, callback=lambda func: func)
    _module("homeassistant.helpers")
    _module("homeassistant.helpers.entity", EntityCategory=EntityCategory)
    _module("homeassistant.helpers.aiohttp_client", async_create_clientsession=None)
    _module("homeassistant.util", slugify=lambda value: str(value).lower().replace(" ", "_"))
    _module("voluptuous", Schema=lambda schema: schema, Required=lambda key, **kw: key)

    custom_components = _module("custom_components")
    custom_components.__path__ = []
    traeger_pkg = _module("custom_components.traeger")
    traeger_pkg.__path__ = []

    class TraegerBaseEntity:
        def __init__(self, client, grill_id, name=None, *, coordinator=None):
            self.client = client
            self.grill_id = grill_id
            self.coordinator = coordinator
            self._attr_name = name

        @property
        def grill_state(self):
            return self.coordinator.data.get(self.grill_id)

        @property
        def grill_units(self):
            return self.client.get_units_for_device(self.grill_id)

    _module("custom_components.traeger.entity", TraegerBaseEntity=TraegerBaseEntity)
    _module("custom_components.traeger.coordinator", TraegerCoordinator=object)
    _module("custom_components.traeger.monitor", TraegerGrillMonitor=object)
    _module("custom_components.traeger.traeger", traeger=object)

    # Real constants so GRILL_MAX_TEMP_* are exercised, not re-declared here.
    _load_local("const")


class _Coordinator:
    def __init__(self, state):
        self.data = {"grill-1": state, "grill-2": state}


class _Client:
    def __init__(self, units):
        self._units = units

    def get_units_for_device(self, grill_id):
        return self._units


def _climate(units, state):
    _install_stubs()
    module = _load_local("climate")
    return module.TraegerGrill(_Client(units), "grill-1", coordinator=_Coordinator(state))


def _ambient_sensor(units, state):
    _install_stubs()
    module = _load_local("sensor")
    return module.TraegerSensor(
        _Coordinator(state),
        _Client(units),
        "grill-1",
        "Ambient Temperature",
        "ambient",
        None,
        device_class=module.SensorDeviceClass.TEMPERATURE,
    )


# --- climate: min/max fallbacks ------------------------------------------------


@pytest.mark.parametrize(
    ("units", "expected_min", "expected_max"),
    [(CELSIUS, 75, 250), (FAHRENHEIT, 165, 500)],
)
def test_empty_limits_fall_back_to_min_and_max_constants(units, expected_min, expected_max):
    grill = _climate(units, {"status": {"connected": True}, "limits": {}})

    assert grill.min_temp == expected_min
    # Regression: max_temp used to fall back to GRILL_MIN_TEMP_*.
    assert grill.max_temp == expected_max


def test_missing_limits_key_falls_back_to_constants():
    grill = _climate(CELSIUS, {"status": {"connected": True}})

    assert (grill.min_temp, grill.max_temp) == (75, 250)


def test_fahrenheit_grill_limits_are_unchanged():
    grill = _climate(
        FAHRENHEIT,
        {"status": {"connected": True}, "limits": {"min_grill_temp": 165, "max_grill_temp": 500}},
    )

    assert grill.min_temp == 165
    assert grill.max_temp == 500


def test_celsius_grill_converts_real_payload_limits():
    # Real payload from a Celsius grill (status.units == 0): max_grill_temp is
    # 500 (degrees F) and there is no min_grill_temp.
    grill = _climate(CELSIUS, {"status": {"units": 0}, "limits": {"max_grill_temp": 500}})

    assert grill.max_temp == 250
    assert grill.min_temp == 75  # falls back to GRILL_MIN_TEMP_C


def test_celsius_grill_converts_both_fahrenheit_limits():
    grill = _climate(
        CELSIUS,
        {"status": {"units": 0}, "limits": {"min_grill_temp": 165, "max_grill_temp": 500}},
    )

    assert grill.min_temp == 74
    assert grill.max_temp == 250


def test_celsius_grill_leaves_limits_already_in_celsius():
    grill = _climate(
        CELSIUS,
        {"status": {"units": 0}, "limits": {"min_grill_temp": 75, "max_grill_temp": 250}},
    )

    assert grill.min_temp == 75
    assert grill.max_temp == 250


# --- climate: entity identifiers (upstream PR #23) -----------------------------


def test_grill_unique_id_is_interpolated_per_grill():
    _install_stubs()
    module = _load_local("climate")
    client = _Client(FAHRENHEIT)
    coordinator = _Coordinator({})

    first = module.TraegerGrill(client, "grill-1", coordinator=coordinator)
    second = module.TraegerGrill(client, "grill-2", coordinator=coordinator)

    assert first.unique_id == "grill-1_climate"
    assert second.unique_id == "grill-2_climate"
    # HA assigns entity_id from the registry; it must not be set literally.
    assert not hasattr(first, "entity_id")


def test_probe_unique_id_and_name_are_interpolated_per_channel():
    _install_stubs()
    module = _load_local("climate")
    client = _Client(FAHRENHEIT)
    coordinator = _Coordinator({})

    probe_0 = module.TraegerGrillProbe(client, "grill-1", "BT0", coordinator=coordinator)
    probe_1 = module.TraegerGrillProbe(client, "grill-1", "BT1", coordinator=coordinator)

    assert probe_0.unique_id == "grill-1_probe_BT0"
    assert probe_1.unique_id == "grill-1_probe_BT1"
    assert probe_0.name == "Probe BT0"
    assert probe_1.name == "Probe BT1"
    assert not hasattr(probe_0, "entity_id")


# --- sensor: ambient temperature ----------------------------------------------


@pytest.mark.parametrize("units", [CELSIUS, FAHRENHEIT])
def test_ambient_sensor_unit_follows_grill_units(units):
    sensor = _ambient_sensor(units, {"status": {"connected": True, "ambient": 30}})

    assert sensor.native_unit_of_measurement == units
    assert sensor.native_value == 30


def test_ambient_sensor_has_temperature_device_class():
    sensor = _ambient_sensor(CELSIUS, {"status": {"connected": True, "ambient": 30}})

    assert sensor._attr_device_class == "temperature"


def test_non_temperature_sensor_keeps_its_configured_unit():
    _install_stubs()
    module = _load_local("sensor")
    sensor = module.TraegerSensor(
        _Coordinator({"status": {"connected": True, "pellet_level": 50}}),
        _Client(CELSIUS),
        "grill-1",
        "Pellet Level",
        "pellet_level",
        "%",
    )

    assert sensor.native_unit_of_measurement == "%"


# --- config flow (upstream PR #22) ---------------------------------------------


def test_options_flow_does_not_assign_config_entry():
    """HA 2025.12 removed the config_entry setter; assigning it raises."""
    _install_stubs()
    config_flow = _load_local("config_flow")

    entry = types.SimpleNamespace(options={"sensor": True}, data={"username": "u"})
    handler = config_flow.BlueprintOptionsFlowHandler(entry)

    assert handler.options == {"sensor": True}
