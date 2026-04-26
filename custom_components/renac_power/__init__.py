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
    DEFAULT_SCAN_INTERVAL_FAST,
    DEFAULT_SCAN_INTERVAL_SLOW,
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


def _make_update_fn(client: RenacApiClient, fetch_method: str, first_fetch_ref: list[bool]):
    async def async_update_data() -> dict:
        try:
            data = await getattr(client, fetch_method)()
        except RenacApiError as err:
            raise UpdateFailed(str(err)) from err
        if first_fetch_ref[0]:
            first_fetch_ref[0] = False
            for endpoint, payload in data.items():
                if isinstance(payload, dict) and "error" not in payload:
                    _LOGGER.debug("Endpoint '%s' top-level keys: %s", endpoint, list(payload.keys()))
                elif isinstance(payload, dict):
                    _LOGGER.warning("Endpoint '%s' returned error: %s", endpoint, payload.get("error"))
                else:
                    _LOGGER.debug("Endpoint '%s' returned type: %s", endpoint, type(payload).__name__)
        return data
    return async_update_data


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

    coordinator_fast = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_fast",
        update_method=_make_update_fn(client, "async_fetch_fast", [True]),
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_FAST),
    )

    coordinator_slow = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_slow",
        update_method=_make_update_fn(client, "async_fetch_slow", [True]),
        update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SLOW),
    )

    await coordinator_fast.async_refresh()
    await coordinator_slow.async_refresh()

    # Auto-discover inverter SN from equipment list if not configured
    if not client.equ_sn and coordinator_slow.data:
        sn = _find_inverter_sn(coordinator_slow.data.get("equipment_list", {}))
        if sn:
            client.equ_sn = sn
            _LOGGER.info("Auto-discovered inverter SN: %s — set RENAC_EQU_SN to enable extra sensors", sn)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinator_fast": coordinator_fast,
        "coordinator_slow": coordinator_slow,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
