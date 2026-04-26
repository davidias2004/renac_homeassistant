from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RenacEntity


def find_value(data: Any, names: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in names and value not in (None, ""):
                return value
        for value in data.values():
            found = find_value(value, names)
            if found not in (None, ""):
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_value(item, names)
            if found not in (None, ""):
                return found
    return None


@dataclass(frozen=True, kw_only=True)
class RenacSensorDescription(SensorEntityDescription):
    source: str
    fields: tuple[str, ...]


SENSORS: tuple[RenacSensorDescription, ...] = (
    RenacSensorDescription(
        key="current_power",
        name="Current Power",
        source="power_flow",
        fields=("power", "pac", "currentPower", "now_power", "real_power", "total_power"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="battery_soc",
        name="Battery SOC",
        source="storage_overview",
        fields=("soc", "battery_soc", "batSoc", "batterySoc", "battery_capacity"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="today_energy",
        name="Today Energy",
        source="chart_day",
        fields=("today_energy", "day_energy", "etoday", "eToday", "power_generation", "generation"),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    RenacSensorDescription(
        key="month_energy",
        name="Month Energy",
        source="chart_month",
        fields=("month_energy", "emonth", "eMonth", "generation"),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="year_energy",
        name="Year Energy",
        source="chart_year",
        fields=("year_energy", "eyear", "eYear", "generation"),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="total_savings",
        name="Total Savings",
        source="savings",
        fields=("saving", "savings", "total_saving", "income", "total_income"),
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="online_equipment",
        name="Online Equipment",
        source="equip_stat",
        fields=("online", "onlineNum", "online_num", "normal", "normalNum"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="error_count",
        name="Error Count",
        source="errors",
        fields=("total", "count", "recordsTotal", "rows"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    async_add_entities(RenacSensor(coordinator, entry, description) for description in SENSORS)


class RenacSensor(RenacEntity, SensorEntity):
    entity_description: RenacSensorDescription

    def __init__(self, coordinator, entry, description: RenacSensorDescription) -> None:
        super().__init__(coordinator, entry, description.key)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data['station_id']}_{description.key}"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.entity_description.source, {})
        value = find_value(data, self.entity_description.fields)
        if isinstance(value, list):
            return len(value)
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data.get(self.entity_description.source, {})
        if isinstance(data, dict) and "error" in data:
            return {"error": data["error"]}
        return {"source": self.entity_description.source}
