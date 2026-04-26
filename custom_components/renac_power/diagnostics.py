from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

TO_REDACT = {"username", "password", "token", "user_id", "station_id", "equ_sn"}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    return {
        "entry": {k: ("REDACTED" if k in TO_REDACT else v) for k, v in entry.data.items()},
        "data_keys": list((coordinator.data or {}).keys()),
    }
