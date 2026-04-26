from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RenacApiClient, RenacApiError
from .const import (
    CONF_BASE_URL,
    CONF_EQU_SN,
    CONF_STATION_ID,
    CONF_USER_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]
_SN_KEYS = ("equ_sn", "equSn", "sn", "serialNumber", "serial_number", "deviceSn", "inverterSn", "equipSn")


def _find_inverter_sn(data: Any) -> str | None:
    items: list = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "rows", "list", "records"):
            if isinstance(data.get(key), list):
                items = data[key]
                break
    for item in items:
        if isinstance(item, dict):
            for k in _SN_KEYS:
                if item.get(k):
                    return str(item[k])
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    client = RenacApiClient(
        session=session,
        base_url=entry.data[CONF_BASE_URL],
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        station_id=str(entry.data[CONF_STATION_ID]),
        user_id=str(entry.data[CONF_USER_ID]),
        equ_sn=entry.data.get(CONF_EQU_SN) or None,
    )

    _first_fetch = True

    async def async_update_data() -> dict:
        nonlocal _first_fetch
        try:
            data = await client.async_fetch_all()
        except RenacApiError as err:
            raise UpdateFailed(str(err)) from err
        if _first_fetch:
            _first_fetch = False
            for endpoint, payload in data.items():
                if isinstance(payload, dict) and "error" not in payload:
                    _LOGGER.debug("Endpoint '%s' top-level keys: %s", endpoint, list(payload.keys()))
                elif isinstance(payload, dict):
                    _LOGGER.warning("Endpoint '%s' returned error: %s", endpoint, payload.get("error"))
                else:
                    _LOGGER.debug("Endpoint '%s' returned type: %s", endpoint, type(payload).__name__)
        return data

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
    )

    # Use async_refresh instead of async_config_entry_first_refresh so the entry loads
    # even if the first API call fails (entities will be unavailable until data arrives).
    await coordinator.async_refresh()

    # Auto-discover inverter SN from equipment list if not configured
    if not client.equ_sn and coordinator.data:
        sn = _find_inverter_sn(coordinator.data.get("equipment_list", {}))
        if sn:
            client.equ_sn = sn
            _LOGGER.info("Auto-discovered inverter SN: %s — set RENAC_EQU_SN to enable extra sensors", sn)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator": coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
