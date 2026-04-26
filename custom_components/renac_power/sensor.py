from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import RenacEntity

_LOGGER = logging.getLogger(__name__)


def find_value(data: Any, names: tuple[str, ...]) -> Any:
    """Find the first occurrence of any of the given field names in nested data."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in names and value not in (None, "", "NoneType"):
                return value
        for value in data.values():
            found = find_value(value, names)
            if found not in (None, "", "NoneType"):
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_value(item, names)
            if found not in (None, "", "NoneType"):
                return found
    return None


@dataclass(frozen=True, kw_only=True)
class RenacSensorDescription(SensorEntityDescription):
    source: str
    fields: tuple[str, ...]


SENSORS: tuple[RenacSensorDescription, ...] = (
    # ── Real-time power ──────────────────────────────────────────────────
    # currentPower is in Watts (e.g. 1964.0 W for a 2.2 kWp system)
    RenacSensorDescription(
        key="pv_power",
        name="PV Power",
        source="station_overview",
        fields=("currentPower",),
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # ── Daily energy ─────────────────────────────────────────────────────
    RenacSensorDescription(
        key="today_energy",
        name="Today Energy",
        source="station_overview",
        fields=("dayPower",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # ── Lifetime energy ──────────────────────────────────────────────────
    RenacSensorDescription(
        key="total_energy",
        name="Total Energy",
        source="station_overview",
        fields=("totalPower",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # ── Monthly / yearly energy (from statistics endpoint) ───────────────
    RenacSensorDescription(
        key="month_energy",
        name="Month Energy",
        source="statistics",
        fields=("month_power_total",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="year_energy",
        name="Year Energy",
        source="statistics",
        fields=("year_power_total",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    # ── Financial savings ─────────────────────────────────────────────────
    RenacSensorDescription(
        key="total_savings",
        name="Total Savings",
        source="savings",
        fields=("profit",),
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="month_savings",
        name="Month Savings",
        source="statistics",
        fields=("total_month_price",),
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="year_savings",
        name="Year Savings",
        source="statistics",
        fields=("total_year_price",),
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="today_savings",
        name="Today Savings",
        source="statistics",
        fields=("total_day_price",),
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
    ),
    # ── Environmental ─────────────────────────────────────────────────────
    RenacSensorDescription(
        key="co2_saved",
        name="CO2 Saved",
        source="savings",
        fields=("co2",),
        native_unit_of_measurement="kg",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    RenacSensorDescription(
        key="trees_saved",
        name="Trees Saved",
        source="savings",
        fields=("tree",),
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="coal_saved",
        name="Coal Saved",
        source="savings",
        fields=("coal",),
        native_unit_of_measurement="kg",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="so2_saved",
        name="SO2 Saved",
        source="savings",
        fields=("so2",),
        native_unit_of_measurement="kg",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    # ── Equipment status ──────────────────────────────────────────────────
    RenacSensorDescription(
        key="online_equipment",
        name="Online Equipment",
        source="equip_stat",
        fields=("total_online_equip",),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="alarm_equipment",
        name="Alarm Equipment",
        source="equip_stat",
        fields=("total_alarm_equip",),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="offline_equipment",
        name="Offline Equipment",
        source="equip_stat",
        fields=("total_off_equip",),
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # ── Error count ───────────────────────────────────────────────────────
    RenacSensorDescription(
        key="error_count",
        name="Error Count",
        source="errors",
        fields=("total",),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # ── Storage / battery (disabled by default — useful for battery systems) ─
    RenacSensorDescription(
        key="battery_charge_today",
        name="Battery Charge Today",
        source="storage_today",
        fields=("DAY_BAT_CHARGE",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="battery_discharge_today",
        name="Battery Discharge Today",
        source="storage_today",
        fields=("DAY_BAT_DISCHARGE",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="load_energy_today",
        name="Load Energy Today",
        source="storage_today",
        fields=("DAY_ENERGY_LOAD",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="feedin_energy_today",
        name="Feed-in Energy Today",
        source="storage_today",
        fields=("METER_FEEDIN_DAY",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    RenacSensorDescription(
        key="grid_consumption_today",
        name="Grid Consumption Today",
        source="storage_today",
        fields=("METER_CONSUM_DAY",),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    # Battery SOC — only available on systems with a battery
    RenacSensorDescription(
        key="battery_soc",
        name="Battery SOC",
        source="storage_today",
        fields=("soc", "SOC", "battery_soc", "batSoc"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
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

        if value is None:
            _LOGGER.debug(
                "%s: no value in '%s' for fields %s",
                self.entity_description.key,
                self.entity_description.source,
                self.entity_description.fields,
            )
            return None

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
        if isinstance(data, dict):
            return {
                "source": self.entity_description.source,
                "available_keys": list(data.keys()),
            }
        return {"source": self.entity_description.source}
