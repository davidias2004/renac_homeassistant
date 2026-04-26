from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorEntityDescription, BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RenacEntity
from .sensor import find_value


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator_slow = hass.data[DOMAIN][entry.entry_id]["coordinator_slow"]
    async_add_entities([RenacProblemSensor(coordinator_slow, entry)])


class RenacProblemSensor(RenacEntity, BinarySensorEntity):
    entity_description = BinarySensorEntityDescription(
        key="problem",
        name="Problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
    )

    def __init__(self, coordinator, entry) -> None:
        super().__init__(coordinator, entry, "problem")
        self._attr_unique_id = f"{entry.data['station_id']}_problem"

    @property
    def is_on(self) -> bool:
        errors = self.coordinator.data.get("errors", {})
        total = find_value(errors, ("total",))
        try:
            return int(total) > 0
        except (TypeError, ValueError):
            return False
