from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_REDACT_VALUES = {"username", "password", "token", "user_id", "station_id", "equ_sn",
                  "userId", "stationId", "userName", "loginName", "login_name"}


def _redact(value: Any, key: str = "") -> Any:
    if key.lower() in {k.lower() for k in _REDACT_VALUES}:
        return "REDACTED"
    if isinstance(value, dict):
        return {k: _redact(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(i) for i in value[:3]]  # only first 3 items to keep it readable
    return value


def _field_map(data: Any, depth: int = 0) -> Any:
    """Return the structure of a response: field names with their types/values (redacted)."""
    if depth > 3:
        return "..."
    if isinstance(data, dict):
        return {k: _field_map(_redact(v, k), depth + 1) for k, v in data.items()}
    if isinstance(data, list):
        if not data:
            return []
        return [_field_map(data[0], depth + 1), f"... ({len(data)} items)"]
    return type(data).__name__ if data is None else repr(data)[:80]


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    raw: dict[str, Any] = coordinator.data or {}

    sensor_status: dict[str, Any] = {}
    for key, source_data in raw.items():
        if isinstance(source_data, dict) and "error" in source_data:
            sensor_status[key] = {"status": "error", "detail": source_data["error"]}
        else:
            sensor_status[key] = {"status": "ok", "fields": _field_map(source_data)}

    return {
        "entry": {k: ("REDACTED" if k in _REDACT_VALUES else v) for k, v in entry.data.items()},
        "endpoints": sensor_status,
    }
