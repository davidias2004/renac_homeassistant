from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfElectricPotential, UnitOfTemperature, PERCENTAGE
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


def sum_values(data: Any, names: tuple[str, ...]) -> float | None:
    """Sum all occurrences of a field name across a nested list structure."""
    total = 0.0
    found = False
    if isinstance(data, dict):
        for key, value in data.items():
            if key in names and value not in (None, "", "NoneType"):
                try:
                    total += float(value)
                    found = True
                except (TypeError, ValueError):
                    pass
            else:
                sub = sum_values(value, names)
                if sub is not None:
                    total += sub
                    found = True
    elif isinstance(data, list):
        for item in data:
            sub = sum_values(item, names)
            if sub is not None:
                total += sub
                found = True
    return round(total, 3) if found else None


@dataclass(frozen=True, kw_only=True)
class RenacSensorDescription(SensorEntityDescription):
    source: str
    fields: tuple[str, ...]
    aggregate: str | None = None  # "sum" to aggregate across list items


SENSORS: tuple[RenacSensorDescription, ...] = (
    # ── Real-time power (power_flow) ─────────────────────────────────────
    RenacSensorDescription(
        key="pv_power",
        name="PV Power",
        source="power_flow",
        fields=("sys_pv_power", "pv1_POWER", "pv2_POWER", "pac", "currentPower"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="grid_power",
        name="Grid Power",
        source="power_flow",
        fields=("grid_POWER", "sys_grid_power", "feedin_POWER"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="load_power",
        name="Load Power",
        source="power_flow",
        fields=("sys_load_power", "power_LOAD", "ups_CT_TOTAL"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="battery_power",
        name="Battery Power",
        source="power_flow",
        fields=("battery1_POWER", "sys_bat_power"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="feedin_power",
        name="Feed-in Power",
        source="power_flow",
        fields=("feedin_POWER", "eps_POWER"),
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # ── Battery ──────────────────────────────────────────────────────────
    RenacSensorDescription(
        key="battery_soc",
        name="Battery SOC",
        source="power_flow",
        fields=("battery1_CAPACITY", "soc", "battery_soc", "batSoc"),
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    RenacSensorDescription(
        key="battery_voltage",
        name="Battery Voltage",
        source="power_flow",
        fields=("battery1_VOL",),
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # ── Energy (power_flow gives today + lifetime totals) ─────────────────
    RenacSensorDescription(
        key="today_energy",
        name="Today Energy",
        source="power_flow",
        fields=("pv_ENERGY_DAY", "energy_DAY", "eToday", "etoday"),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    RenacSensorDescription(
        key="total_energy",
        name="Total Energy",
        source="power_flow",
        fields=("energy_TOTAL", "pv_ENERGY_TOTAL", "eTotal"),
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # ── Monthly / yearly (sum across daily list) ──────────────────────────
    RenacSensorDescription(
        key="month_energy",
        name="Month Energy",
        source="chart_month",
        fields=("DAY_PV_ENERGY", "DAY_ENERGY_SOLAR"),
        aggregate="sum",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="year_energy",
        name="Year Energy",
        source="chart_year",
        fields=("DAY_PV_ENERGY", "DAY_ENERGY_SOLAR"),
        aggregate="sum",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    # ── Savings ───────────────────────────────────────────────────────────
    RenacSensorDescription(
        key="total_savings",
        name="Total Savings",
        source="savings",
        fields=("profit", "saving", "income", "total_saving"),
        state_class=SensorStateClass.TOTAL,
    ),
    RenacSensorDescription(
        key="co2_saved",
        name="CO2 Saved",
        source="savings",
        fields=("co2",),
        native_unit_of_measurement="kg",
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    # ── Inverter diagnostics ──────────────────────────────────────────────
    RenacSensorDescription(
        key="inverter_temperature",
        name="Inverter Temperature",
        source="power_flow",
        fields=("inv_TEMPERATURE",),
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # ── Equipment / errors (require valid user_id) ────────────────────────
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

        if self.entity_description.aggregate == "sum":
            value = sum_values(data, self.entity_description.fields)
        else:
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
