"""Example commands sensor: how many sentences work; topic sentences in attributes.

The content comes from assist/router_examples.yaml (action assist_router.generate_examples).
Attributes with sentence lists are not recorded in history (recorder).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from . import RuntimeData, examples
from .const import DOMAIN, SIGNAL_EXAMPLES, SIGNAL_LOG

LAST_ROWS = 20  # latest log entries in the sensor attribute


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[RuntimeData],
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ExamplesSensor(entry), UnrecognizedSensor(entry)])


class ExamplesSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_translation_key = "examples"
    _attr_icon = "mdi:format-list-checks"
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({"topics", "rejected"})

    def __init__(self, entry: ConfigEntry[RuntimeData]) -> None:
        self._path = entry.runtime_data.router.path.with_name(examples.EXAMPLES_FILE)
        self._attr_unique_id = f"{entry.entry_id}-examples"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._data: dict[str, Any] = {}
        self._generated: datetime | None = None

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_EXAMPLES, self._reload))
        await self._async_read()

    @callback
    def _reload(self) -> None:
        self.hass.async_create_task(self._async_read())

    async def _async_read(self) -> None:
        self._data = await self.hass.async_add_executor_job(examples.load, self._path)
        try:
            mtime = await self.hass.async_add_executor_job(lambda: self._path.stat().st_mtime)
        except OSError:
            self._generated = None
        else:
            self._generated = dt_util.utc_from_timestamp(mtime)
        self.async_write_ha_state()

    @property
    def native_value(self) -> int | None:
        if not self._data:
            return None
        return sum(len(examples.working(t)) for t in self._data.values() if isinstance(t, dict))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        topics = {
            name: examples.working(t) for name, t in self._data.items() if isinstance(t, dict)
        }
        rejected = {
            name: len(examples.rejected(t)) for name, t in self._data.items() if isinstance(t, dict)
        }
        return {
            "file": str(self._path),
            "generated": self._generated.isoformat() if self._generated else None,
            "topics": topics,
            "rejected": rejected,
        }


class UnrecognizedSensor(SensorEntity):
    """Unrecognized log: number of entries, latest entries in the `last` attribute."""

    _attr_has_entity_name = True
    _attr_translation_key = "unrecognized"
    _attr_icon = "mdi:comment-question-outline"
    _attr_should_poll = False
    _unrecorded_attributes = frozenset({"last"})

    def __init__(self, entry: ConfigEntry[RuntimeData]) -> None:
        self._log = entry.runtime_data.log
        self._attr_unique_id = f"{entry.entry_id}-unrecognized"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._rows: list[dict[str, str]] = []

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(self.hass, SIGNAL_LOG, self._reload))
        await self._async_read()

    @callback
    def _reload(self) -> None:
        self.hass.async_create_task(self._async_read())

    async def _async_read(self) -> None:
        self._rows = await self._log.async_rows()
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._rows)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        last = [
            {k: row.get(k, "") for k in ("timestamp", "area", "speaker", "text", "response")}
            for row in reversed(self._rows[-LAST_ROWS:])
        ]
        return {"file": str(self._log.path), "last": last}
