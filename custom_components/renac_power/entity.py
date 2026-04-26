from __future__ import annotations

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class RenacEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, entry, key: str) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.key = key
        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(entry.data["station_id"]))},
            "name": f"RENAC Station {entry.data['station_id']}",
            "manufacturer": "RENAC",
            "model": "Cloud API",
        }
