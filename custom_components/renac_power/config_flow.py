from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RenacApiClient, RenacApiError
from .const import CONF_BASE_URL, CONF_EQU_SN, CONF_STATION_ID, CONF_USER_ID, DEFAULT_BASE_URL, DOMAIN

_LOGGER = logging.getLogger(__name__)

# Confirmed working: POST /api/station/list {"user_id":149502,"offset":0,"rows":1}
_STATION_LIST_ENDPOINTS = [
    "/api/station/list",
    "/api/home/station/list",
    "/api/user/station/list",
    "/bg/station/list",
    "/api/home/stationList",
]
_STATION_ID_KEYS = ("stationId", "station_id", "sid", "plantId", "plant_id")
_STATION_NAME_KEYS = ("stationName", "station_name", "name", "plantName", "plant_name")
_USER_ID_KEYS = ("userId", "user_id", "uid", "memberId", "member_id")
_EQU_SN_KEYS = ("equ_sn", "equSn", "sn", "serialNumber", "serial_number", "deviceSn", "inverterSn", "equipSn")


def _deep_find_key(data: Any, keys: tuple[str, ...]) -> Any:
    if isinstance(data, dict):
        for k in keys:
            if k in data and data[k] not in (None, ""):
                return data[k]
        for v in data.values():
            found = _deep_find_key(v, keys)
            if found is not None:
                return found
    if isinstance(data, list):
        for item in data:
            found = _deep_find_key(item, keys)
            if found is not None:
                return found
    return None


def _extract_user_id(login_data: dict) -> str | None:
    """Extract user_id from login response.

    RENAC returns the user_id as the root 'data' field:
    {"code": 1, "data": 149502, "user": {"token": "..."}}
    """
    raw = login_data.get("data")
    if isinstance(raw, int) and raw > 0:
        return str(raw)
    if isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
        return raw
    return str(uid) if (uid := _deep_find_key(login_data, _USER_ID_KEYS)) else None


def _extract_station_list(data: Any) -> list[dict[str, Any]]:
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "rows", "list", "records", "stations", "stationList"):
            if isinstance(data.get(key), list):
                items = data[key]
                break

    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = next((item[k] for k in _STATION_ID_KEYS if k in item), None)
        if sid:
            result.append({
                "station_id": str(sid),
                "name": next((item[k] for k in _STATION_NAME_KEYS if k in item), None),
                "user_id": str(uid) if (uid := next((item[k] for k in _USER_ID_KEYS if k in item), None)) else None,
            })
    return result


def _find_equ_sn(data: Any) -> str | None:
    """Extract the first inverter serial number from an equipment list response."""
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
            for k in _EQU_SN_KEYS:
                if item.get(k):
                    return str(item[k])
    return None


async def _discover_equ_sn(client: RenacApiClient, station_id: str, user_id: str) -> str | None:
    """Call /bg/equList and return the first inverter SN found."""
    try:
        resp = await client._request("POST", "/bg/equList", json={
            "user_id": user_id,
            "station_id": station_id,
            "status": 0,
            "offset": 0,
            "rows": 10,
            "equ_sn": "",
        })
        sn = _find_equ_sn(resp)
        if sn:
            _LOGGER.info("Auto-discovered inverter SN: %s", sn)
        return sn
    except RenacApiError as err:
        _LOGGER.debug("Could not auto-discover inverter SN: %s", err)
        return None


class RenacPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._credentials: dict[str, Any] = {}
        self._discovered_stations: list[dict[str, Any]] = []
        self._discovered_user_id: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            temp_client = RenacApiClient(
                session=session,
                base_url=DEFAULT_BASE_URL,
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                station_id="",
                user_id="",
            )
            try:
                login_data = await temp_client._raw_login()
            except RenacApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                self._discovered_user_id = _extract_user_id(login_data)
                self._credentials = {**user_input, CONF_BASE_URL: DEFAULT_BASE_URL}

                # Discover stations — confirmed working payload includes offset+rows
                stations: list[dict[str, Any]] = []
                for endpoint in _STATION_LIST_ENDPOINTS:
                    try:
                        resp = await temp_client._request("POST", endpoint, json={
                            "user_id": self._discovered_user_id or "",
                            "offset": 0,
                            "rows": 10,
                        })
                        stations = _extract_station_list(resp)
                        if stations:
                            _LOGGER.debug("Stations found via %s: %s", endpoint, stations)
                            break
                    except RenacApiError:
                        pass

                self._discovered_stations = stations

                if not stations:
                    return await self.async_step_manual()

                # Single station → skip selection, go straight to confirm
                if len(stations) == 1:
                    return await self._confirm_station(temp_client, stations[0])

                return await self.async_step_station()

        schema = vol.Schema({
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def _confirm_station(
        self,
        client: RenacApiClient,
        station: dict[str, Any],
    ):
        """Create the entry for a single auto-selected station."""
        user_id = station.get("user_id") or self._discovered_user_id or ""
        station_id = station["station_id"]
        equ_sn = await _discover_equ_sn(client, station_id, user_id)

        data = {
            **self._credentials,
            CONF_STATION_ID: station_id,
            CONF_USER_ID: user_id,
            CONF_EQU_SN: equ_sn,
        }
        await self.async_set_unique_id(f"{user_id}_{station_id}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"RENAC {station.get('name') or station_id}",
            data=data,
        )

    async def async_step_station(self, user_input: dict[str, Any] | None = None):
        """Let user pick from discovered stations (shown when multiple stations exist)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = next(
                (s for s in self._discovered_stations if s["station_id"] == user_input[CONF_STATION_ID]),
                None,
            )
            user_id = (station or {}).get("user_id") or self._discovered_user_id or user_input.get(CONF_USER_ID, "")
            station_id = user_input[CONF_STATION_ID]

            session = async_get_clientsession(self.hass)
            client = RenacApiClient(
                session=session,
                base_url=self._credentials[CONF_BASE_URL],
                username=self._credentials[CONF_USERNAME],
                password=self._credentials[CONF_PASSWORD],
                station_id=station_id,
                user_id=user_id,
            )
            try:
                await client.async_login()
            except RenacApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                equ_sn = await _discover_equ_sn(client, station_id, user_id)
                data = {
                    **self._credentials,
                    CONF_STATION_ID: station_id,
                    CONF_USER_ID: user_id,
                    CONF_EQU_SN: equ_sn,
                }
                await self.async_set_unique_id(f"{user_id}_{station_id}")
                self._abort_if_unique_id_configured()
                station_name = (station or {}).get("name") or station_id
                return self.async_create_entry(title=f"RENAC {station_name}", data=data)

        station_options = {
            s["station_id"]: f"{s['name'] or s['station_id']} (ID: {s['station_id']})"
            for s in self._discovered_stations
        }
        schema_dict: dict = {vol.Required(CONF_STATION_ID): vol.In(station_options)}
        if not self._discovered_user_id:
            schema_dict[vol.Required(CONF_USER_ID)] = str
        schema = vol.Schema(schema_dict)

        return self.async_show_form(step_id="station", data_schema=schema, errors=errors)

    async def async_step_manual(self, user_input: dict[str, Any] | None = None):
        """Fallback: manual entry of station_id and user_id."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = str(user_input[CONF_STATION_ID])
            user_id = str(user_input[CONF_USER_ID])
            session = async_get_clientsession(self.hass)
            client = RenacApiClient(
                session=session,
                base_url=self._credentials[CONF_BASE_URL],
                username=self._credentials[CONF_USERNAME],
                password=self._credentials[CONF_PASSWORD],
                station_id=station_id,
                user_id=user_id,
            )
            try:
                await client.async_login()
            except RenacApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                equ_sn = await _discover_equ_sn(client, station_id, user_id)
                data = {
                    **self._credentials,
                    CONF_STATION_ID: station_id,
                    CONF_USER_ID: user_id,
                    CONF_EQU_SN: equ_sn,
                }
                await self.async_set_unique_id(f"{user_id}_{station_id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"RENAC {station_id}", data=data)

        schema = vol.Schema({
            vol.Required(CONF_USER_ID, default=self._discovered_user_id or ""): str,
            vol.Required(CONF_STATION_ID): str,
        })
        return self.async_show_form(step_id="manual", data_schema=schema, errors=errors)
