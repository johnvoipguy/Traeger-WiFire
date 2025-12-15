# Copilot Instructions for Traeger WiFire Integration

## Project Overview

This is a Home Assistant custom integration for Traeger WiFire grills. It allows users to monitor and control their Traeger grills through Home Assistant.

**Key Information:**
- **Domain**: `traeger`
- **Integration Type**: Device integration with cloud push IoT class
- **Version**: 1.0.1 (from `manifest.json` - this is the authoritative version for the integration)
  - Note: `const.py` has an older VERSION constant (0.1.0) that may need updating
- **Quality Scale**: Bronze (working towards Silver)
- **Dependencies**: `aiomqtt>=2.1.0,<3`
- **Codeowner**: @johnvoipguy

## Architecture

### Project Structure
```
custom_components/traeger/
├── __init__.py           # Integration setup and entry point
├── climate.py            # Climate entities (grill & probe temperature control)
├── config_flow.py        # Configuration flow for UI setup
├── const.py              # Constants and configuration values
├── coordinator.py        # Data update coordinator
├── entity.py             # Base entity classes
├── manifest.json         # Integration metadata
├── monitor.py            # Grill monitoring logic
├── number.py             # Number entities (timer)
├── select.py             # Select entities
├── sensor.py             # Sensor entities (temperature, state)
├── switch.py             # Switch entities (SuperSmoke, KeepWarm)
├── traeger.py            # Traeger API client
├── pyproject.toml        # Python project configuration
└── quality_scale.yaml    # Home Assistant quality scale tracking
```

### Platform Components
- **Climate**: Main grill temperature control and probe temperature control
- **Sensor**: Temperature readings, grill state, heating state, probe state
- **Switch**: SuperSmoke, KeepWarm, and connectivity switches
- **Number**: Timer control (minutes input)
- **Select**: Various selection controls

## Coding Standards

### Python Style
- **Target Version**: Python 3.13
- **Line Length**: 88 characters (Black-compatible)
- **Linter**: Ruff
- **Import Sorting**: isort with Home Assistant as first-party
- Follow Home Assistant's coding standards

### Import Order
1. Future imports (`from __future__ import annotations`)
2. Standard library
3. Third-party libraries
4. Home Assistant core (`homeassistant.*`)
5. Local imports (`.const`, `.coordinator`, etc.)

### Code Conventions
- Use type hints for all function parameters and return values
- Add docstrings to all public functions and classes
- Use `_LOGGER` for logging (import from `logging` module)
- Prefer `async` functions for I/O operations
- Use `@property` decorators for entity attributes

### Naming Conventions
- Classes: `PascalCase` (e.g., `TraegerGrill`, `TraegerCoordinator`)
- Functions/methods: `snake_case` (e.g., `async_setup_entry`, `get_grills`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `GRILL_MODE_OFFLINE`, `DOMAIN`)
- Private methods: Prefix with `_` (e.g., `_dedupe_entities`)

## Home Assistant Integration Best Practices

### Entity Implementation
1. All entities should extend appropriate base classes from `homeassistant.components`
2. Use `TraegerBaseEntity` as the base for all integration entities
3. Implement unique IDs for all entities using `{grill_id}_{entity_type}`
4. Use the coordinator pattern for data updates
5. Entities should not directly poll; use `TraegerCoordinator` instead

### Configuration Flow
- Use config flow for UI-based setup (no YAML configuration)
- Store credentials securely in config entries
- Required fields: `username`, `password`

### State Management
Follow the state definitions in the README:
- **Grill States**: offline, sleeping, idle, igniting, preheating, manual_cook, custom_cook, cool_down, shutdown, unknown
- **Heating States**: idle, preheating, heating, cooling, at_temp, over_temp, under_temp, cool_down
- **Probe States**: idle, set, close, at_temp, fell_out

### Device Registry
- Each grill should be registered as a device
- Device identifiers use grill's `thingName`
- Include manufacturer, model, and firmware information

## Build, Lint, and Test Commands

### Linting
```bash
# Run Ruff linter (configured in custom_components/traeger/pyproject.toml)
ruff check .
```

### Validation
```bash
# Home Assistant validation (via GitHub Actions)
# Uses hassfest action to validate integration structure
```

### Testing
- Currently no automated tests (contributions welcome!)
- Manual testing required via Home Assistant UI
- Test with actual Traeger grill hardware or mock data

## Development Workflow

### Adding New Features
1. Check if feature requires new entity types or modifies existing ones
2. Update `const.py` for new constants
3. Implement entity logic in appropriate platform file
4. Update `coordinator.py` if new data sources are needed
5. Update documentation if user-facing changes are made

### Modifying Existing Code
- Maintain backward compatibility with existing configurations
- Update `VERSION` in `manifest.json` for releases
- Test with multiple grill models if possible
- Consider impact on existing automations and dashboards

### API Client (`traeger.py`)
- Uses MQTT for real-time updates
- Handles authentication and session management
- Should be resilient to network issues
- Implements exponential backoff for retries

## Common Pitfalls to Avoid

1. **Don't create duplicate entities**: Use `_dedupe_entities` pattern or track added entities
2. **Don't block the event loop**: Always use `async` for I/O operations
3. **Don't log sensitive data**: Avoid logging passwords or personal information
4. **Don't hardcode values**: Use constants from `const.py`
5. **Don't forget unique IDs**: All entities must have stable unique identifiers
6. **Don't poll directly**: Use the coordinator for data updates

## Temperature Handling

- Support both Fahrenheit and Celsius
- Minimum grill temperature: 165°F (75°C) - defined by `GRILL_MIN_TEMP_F` / `GRILL_MIN_TEMP_C`
- Maximum grill temperature: Retrieved from API via `grill_limits.max_grill_temp` (varies by grill model)
- Probe maximum: 212°F (100°C) for meat probe temperature (hardcoded in `TraegerGrillProbe.max_temp`)
- Probe presets available for common foods defined in `PROBE_PRESET_MODES` (Chicken: 165°F/74°C, Beef, Pork, Turkey, Fish)
- Temperature limits come from the grill's API response (`state.limits`) when available
- Always respect user's Home Assistant temperature unit preference

## Integration-Specific Context

### Grill Modes (from `const.py`)
```python
GRILL_MODE_OFFLINE = 99
GRILL_MODE_SHUTDOWN = 9
GRILL_MODE_COOL_DOWN = 8
GRILL_MODE_CUSTOM_COOK = 7
GRILL_MODE_MANUAL_COOK = 6
GRILL_MODE_PREHEATING = 5
GRILL_MODE_IGNITING = 4
GRILL_MODE_IDLE = 3
GRILL_MODE_SLEEPING = 2
```

### Coordinator Pattern
- Use `TraegerCoordinator` for all data updates
- Attach coordinator to client via `client.attach_coordinator(coordinator)`
- Pass coordinator to entity constructors
- Entities should listen to coordinator updates

## Security Considerations

- Never log or expose user credentials
- Store passwords only in config entries (encrypted by Home Assistant)
- Validate all user inputs in config flow
- Handle API errors gracefully without exposing internal details

## Contributing

- Read [CONTRIBUTING.md](../CONTRIBUTING.md) before making changes
- Follow the [Code of Conduct](../CODE_OF_CONDUCT.md)
- Use clear commit messages
- Submit pull requests with detailed descriptions
- Include testing steps for reviewers

## Resources

- **Documentation**: https://github.com/johnvoipguy/hacs-Traeger-WiFire
- **Issue Tracker**: https://github.com/johnvoipguy/hacs-Traeger-WiFire/issues
- **Home Assistant Developer Docs**: https://developers.home-assistant.io/
- **Traeger Website**: https://www.traegergrills.com/

## Quick Reference

### File Locations for Common Tasks
- Add constants: `custom_components/traeger/const.py`
- Modify grill control: `custom_components/traeger/climate.py`
- Add sensors: `custom_components/traeger/sensor.py`
- Update API client: `custom_components/traeger/traeger.py`
- Modify configuration: `custom_components/traeger/config_flow.py`
- Update coordinator: `custom_components/traeger/coordinator.py`

### When to Update What
- **manifest.json**: Add new dependencies, bump version
- **quality_scale.yaml**: Track progress on quality improvements
- **const.py**: Add new modes, states, or configuration options
- **strings.json**: Add user-facing text or translations
