"""Custom integration to integrate Traeger with Home Assistant."""
from __future__ import annotations

import asyncio
import logging
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .coordinator import TraegerCoordinator
from .traeger import traeger as TraegerClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: Final[list[Platform]] = [
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Traeger from a config entry."""
    _LOGGER.debug("Starting Traeger setup for entry: {entry.entry_id}")

    # Create client (your original sequence)
    session = async_get_clientsession(hass)
    client = TraegerClient(
        entry.data["username"],
        entry.data["password"],
        hass,
        session,
    )

    # Create shared coordinator and attach it to the client
    coordinator = TraegerCoordinator(hass, client, entry)
    if hasattr(client, "attach_coordinator"):
        client.attach_coordinator(coordinator)

    # Store both so all platforms reuse the same instances
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    # Prefetch grills so platforms can add entities/devices immediately
    try:
        await asyncio.wait_for(client.update_grills(), timeout=15)
    except Exception as err:
        _LOGGER.debug("Prefetch grills failed: %s", err)
    if not client.get_grills():
        _LOGGER.debug("No grills found during setup; entities would be empty")

    # Start scheduling auto poke for each grill
    for grill in client.get_grills():
        grill_id = grill["thingName"]
        client.schedule_auto_poke(hass, grill_id, interval_seconds=15, idle_threshold_seconds=30)

    # Fast first refresh (snapshot only; no network)
    try:
        await asyncio.wait_for(coordinator.async_config_entry_first_refresh(), timeout=10)
    except Exception as err:
        _LOGGER.debug("Coordinator first refresh failed/timed out: %s", err)

    async def _start(_: object | None = None) -> None:
        """Start cloud/MQTT in background on HA loop."""
        hass.async_create_background_task(
            client.start(), name="{DOMAIN}_client_start", eager_start=True
        )

    if hass.is_running:
        await _start(None)
    else:
        entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.debug("Forwarded setup for platforms: {PLATFORMS}")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug("Unloading Traeger integration for entry: {entry.entry_id}")
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        client = data and data.get("client")
        if client and hasattr(client, "kill"):
            await client.kill()
    _LOGGER.debug("Unloaded Traeger integration for entry: {entry.entry_id}, unload_ok={unload_ok}")
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.debug("Reloading Traeger integration for entry: {entry.entry_id}")
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)
