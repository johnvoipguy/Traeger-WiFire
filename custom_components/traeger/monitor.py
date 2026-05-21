"""Helpers to add accessory-based entities (e.g., probes)."""

from __future__ import annotations

from collections.abc import Callable, Iterable
import logging
from typing import Any

from homeassistant.helpers.entity import Entity

_LOGGER = logging.getLogger(__name__)


class TraegerGrillMonitor:
    def __init__(
        self,
        client: Any,
        grill_id: str,
        async_add_entities: Callable[[list[Entity]], None],
        entity_class: type[Entity],
        *,
        coordinator: Any | None = None,
        include_types: tuple[str, ...] = ("probe",),
    ) -> None:
        """Initialize the grill accessory monitor."""
        self.client = client
        self.grill_id = grill_id
        self.async_add_entities = async_add_entities
        self.entity_class = entity_class
        self.coordinator = coordinator
        self.include_types = include_types

        self._seen_channels: set[str] = set()
        self._unsub: Callable[[], None] | None = None

    def _current_state(self) -> dict[str, Any]:
        """Return latest state for this grill, preferring coordinator snapshot."""
        if self.coordinator and getattr(self.coordinator, "data", None):
            state = self.coordinator.data.get(self.grill_id) or {}
            if state:
                return state
        return self.client.get_state_for_device(self.grill_id) or {}

    @staticmethod
    def _iter_accessories(state: dict[str, Any]) -> Iterable[dict[str, Any]]:
        """Yield accessories from state.status.acc safely."""
        status = state.get("status") or {}
        accessories = status.get("acc") or []
        for acc in accessories:
            if isinstance(acc, dict):
                yield acc

    def _iter_new_channels(self, state: dict[str, Any]) -> Iterable[str]:
        """Yield new accessory channels matching include_types."""
        for acc in self._iter_accessories(state):
            if acc.get("type") not in self.include_types:
                continue
            channel = acc.get("uuid") or acc.get("channel")
            if not channel or not isinstance(channel, str):
                _LOGGER.debug(
                    f"Skipping accessory with missing/invalid channel on grill {self.grill_id}: {acc}"
                )
                continue
            if channel in self._seen_channels:
                continue
            yield channel

    def _make_entity(self, channel: str) -> Entity:
        """Instantiate an entity for a specific channel."""
        try:
            # New-style entities accepting coordinator kwarg
            return self.entity_class(
                self.client, self.grill_id, channel, coordinator=self.coordinator
            )
        except TypeError:
            # Legacy entities without coordinator kwarg
            return self.entity_class(self.client, self.grill_id, channel)

    def _add_new_from_state(self, state: dict[str, Any]) -> int:
        """Create and add entities for channels not yet seen. Returns count."""
        new_entities: list[Entity] = []
        for channel in self._iter_new_channels(state):
            entity = self._make_entity(channel)
            _LOGGER.debug(
                f"Discovered {self.entity_class.__name__} on grill {self.grill_id}: channel={channel}"
            )
            new_entities.append(entity)
            self._seen_channels.add(channel)

        if new_entities:
            _LOGGER.debug(
                f"Monitor for grill {self.grill_id} adding {len(new_entities)} entity(ies)"
            )
            self.async_add_entities(new_entities)

        return len(new_entities)

    def _on_coordinator_update(self) -> None:
        """Handle coordinator data updates by adding new entities if needed."""
        try:
            state = self._current_state()
            added = self._add_new_from_state(state)
            if added:
                _LOGGER.debug(
                    f"Monitor for grill {self.grill_id} added {added} new entity(ies) from coordinator update"
                )
        except Exception:  # Best-effort; never raise from callbacks
            _LOGGER.exception("Monitor update failed for grill {self.grill_id}")

    async def async_setup(self) -> None:
        """Discover accessories and add entities. Subscribe for future updates."""
        _LOGGER.debug(
            f"Setting up probe monitor for grill {self.grill_id} using {self.entity_class.__name__}"
        )

        # Initial discovery from latest available state
        state = self._current_state()
        self._add_new_from_state(state)

        # Subscribe to coordinator updates for dynamic additions
        if self.coordinator and hasattr(self.coordinator, "async_add_listener"):
            self._unsub = self.coordinator.async_add_listener(self._on_coordinator_update)
            _LOGGER.debug(
                f"Probe monitor subscribed to coordinator updates for grill {self.grill_id}"
            )

    def shutdown(self) -> None:
        """Unsubscribe from coordinator updates."""
        if self._unsub:
            try:
                self._unsub()
            finally:
                self._unsub = None
