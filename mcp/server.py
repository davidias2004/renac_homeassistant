#!/usr/bin/env python3
"""RENAC Power MCP Server — exposes the RENAC cloud API as MCP tools."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import aiohttp
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("renac-power", dependencies=["aiohttp"])

# ---------------------------------------------------------------------------
# Standalone API client (no Home Assistant dependency)
# ---------------------------------------------------------------------------

class RenacApiError(Exception):
    """RENAC API error."""


_STATION_LIST_ENDPOINTS = [
    "/api/home/station/list",
    "/api/station/list",
    "/api/user/station/list",
    "/bg/station/list",
    "/api/home/stationList",
    "/api/stationList",
]

_USER_ID_KEYS = ("userId", "user_id", "id", "uid", "memberId", "member_id")
_STATION_ID_KEYS = ("stationId", "station_id", "id", "sid", "plantId", "plant_id")
_STATION_NAME_KEYS = ("stationName", "station_name", "name", "plantName", "plant_name")


@dataclass
class RenacClient:
    base_url: str
    username: str
    password: str
    station_id: str = ""
    user_id: str = ""
    equ_sn: str | None = None
    token: str | None = field(default=None, repr=False)
    _login_data: dict[str, Any] = field(default_factory=dict, init=False, repr=False)
    _session: aiohttp.ClientSession | None = field(default=None, init=False, repr=False)

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def login(self) -> str:
        data = await self._request(
            "POST",
            "/api/user/login",
            json={"login_name": self.username, "pwd": self.password},
            auth_required=False,
        )
        token = _deep_find(data, ["user.token", "token", "access_token", "data.token", "data.access_token"])
        if not token:
            raise RenacApiError(f"Login OK but token not found in response: {data}")
        self.token = str(token)
        self._login_data = data if isinstance(data, dict) else {}

        # Auto-discover user_id from login response if not configured
        # Pattern: {"code": 1, "data": 149502, "user": {"token": "..."}} — data IS the user_id
        if not self.user_id and isinstance(data, dict):
            raw = data.get("data")
            if isinstance(raw, int) and raw > 0:
                self.user_id = str(raw)
            elif isinstance(raw, str) and raw.isdigit() and int(raw) > 0:
                self.user_id = raw
            else:
                uid = _deep_find(data, [f"data.{k}" for k in _USER_ID_KEYS] + list(_USER_ID_KEYS))
                if uid:
                    self.user_id = str(uid)

        return self.token

    async def discover_stations(self) -> dict[str, Any]:
        """Try known endpoints to find the station list for this account."""
        await self._ensure_auth()
        result: dict[str, Any] = {
            "login_response": self._login_data,
            "user_id_discovered": self.user_id or None,
            "station_endpoints": {},
        }

        for endpoint in _STATION_LIST_ENDPOINTS:
            for payload in [
                {"user_id": self.user_id},
                {"userId": self.user_id},
                {},
            ]:
                try:
                    resp = await self._request("POST", endpoint, json=payload)
                    result["station_endpoints"][endpoint] = resp
                    break
                except RenacApiError:
                    pass

        # Extract a clean station summary for convenience
        stations = []
        for endpoint_data in result["station_endpoints"].values():
            found = _extract_stations(endpoint_data)
            if found:
                stations = found
                break
        result["stations_summary"] = stations
        return result

    async def _ensure_auth(self) -> None:
        if not self.token:
            await self.login()

    async def _request(
        self,
        method: str,
        path: str,
        json: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth_required: bool = True,
    ) -> Any:
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        req_headers: dict[str, str] = {
            "accept": "application/json, text/plain, */*",
            "Referer": "https://sec.eu.renacpower.com/",
        }
        if json is not None:
            req_headers["content-type"] = "application/json;charset=UTF-8"
        if headers:
            req_headers.update(headers)
        if auth_required:
            await self._ensure_auth()
            req_headers["token"] = self.token or ""

        session = self._get_session()
        async with session.request(
            method, url, json=json, data=data, headers=req_headers, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RenacApiError(f"HTTP {resp.status} at {path}: {text[:400]}")
            try:
                payload = await resp.json(content_type=None)
            except Exception as err:
                raise RenacApiError(f"Non-JSON response at {path}: {text[:400]}") from err

        if isinstance(payload, dict):
            code = payload.get("code") or payload.get("status")
            msg = payload.get("msg") or payload.get("message")
            if code in (401, 403, "401", "403"):
                raise RenacApiError(f"Invalid/expired token at {path}: {msg or payload}")
        return payload

    async def _authed_post(self, path: str, payload: dict[str, Any], form: bool = False) -> Any:
        """POST with automatic token refresh on 401."""
        try:
            if form:
                return await self._request(
                    "POST", path, data=payload,
                    headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
                )
            return await self._request("POST", path, json=payload)
        except RenacApiError as err:
            if "token" in str(err).lower() or "401" in str(err) or "403" in str(err):
                await self.login()
                if form:
                    return await self._request(
                        "POST", path, data=payload,
                        headers={"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
                    )
                return await self._request("POST", path, json=payload)
            raise

    # ------------------------------------------------------------------
    # Domain methods
    # ------------------------------------------------------------------

    async def get_station_overview(self) -> dict[str, Any]:
        """Current power + today/total energy from the dashboard API."""
        return await self._authed_post(
            "/api/dashboard/pageStation",
            {"email": self.user_id, "offset": 0, "rows": 5},
        )

    async def get_statistics(self) -> dict[str, Any]:
        """Month/year/lifetime energy totals and financial summary."""
        return await self._authed_post(
            "/api/dashboard/large/v2/statistics",
            {"email": self.user_id},
        )

    async def get_storage_overview(self) -> dict[str, Any]:
        return await self._authed_post(
            "/api/station/storage/overview", {"station_id": self.station_id}
        )

    async def get_savings(self) -> dict[str, Any]:
        return await self._authed_post(
            "/api/station/all/savings", {"station_id": self.station_id}
        )

    async def get_equipment_status(self) -> dict[str, Any]:
        return await self._authed_post(
            "/api/station/equipStat", {"station_id": self.station_id, "user_id": self.user_id}
        )

    async def get_errors(
        self, rows: int = 20, status: str = "0", offset: int = 0
    ) -> dict[str, Any]:
        today = date.today().isoformat()
        return await self._authed_post(
            "/api/home/errorList2",
            {
                "user_id": self.user_id,
                "begin_time": today,
                "end_time": today,
                "offset": offset,
                "rows": rows,
                "station_id": self.station_id,
                "status": status,
            },
        )

    async def get_chart_day(self, day: str | None = None) -> dict[str, Any]:
        return await self._authed_post(
            "/api/station/chart/station",
            {"time_type": 1, "station_id": self.station_id, "time": day or date.today().isoformat()},
        )

    async def get_chart_month(self, month: str | None = None) -> dict[str, Any]:
        return await self._authed_post(
            "/api/station/chart/station",
            {"time_type": 3, "station_id": self.station_id, "time": month or date.today().isoformat()[:7]},
        )

    async def get_chart_year(self, year: str | None = None) -> dict[str, Any]:
        return await self._authed_post(
            "/api/station/chart/station",
            {"time_type": 4, "station_id": self.station_id, "time": year or date.today().isoformat()[:4]},
        )

    async def get_equipment_list(self, rows: int = 20, offset: int = 0) -> dict[str, Any]:
        return await self._authed_post(
            "/bg/equList",
            {
                "user_id": self.user_id,
                "station_id": self.station_id,
                "status": 0,
                "offset": offset,
                "rows": rows,
                "equ_sn": "",
            },
        )

    async def get_inverter_detail(self, equ_sn: str | None = None) -> dict[str, Any]:
        sn = equ_sn or self.equ_sn
        if not sn:
            raise RenacApiError("equ_sn is required for inverter detail")
        today = date.today().isoformat()
        return await self._authed_post(
            "/bg/inv/detail", {"equ_sn": sn, "offset": 0, "rows": 10, "time": today}
        )

    async def get_grid_chart(self, equ_sn: str | None = None) -> dict[str, Any]:
        sn = equ_sn or self.equ_sn
        if not sn:
            raise RenacApiError("equ_sn is required for grid chart")
        return await self._authed_post(
            "/api/inv/gridChart2",
            {"equipSn": sn, "timeType": 1, "time": date.today().isoformat(), "temId": 6},
        )

    async def fetch_all(self) -> dict[str, Any]:
        """Fetch all available data."""
        tasks: dict[str, Any] = {
            "station_overview": self.get_station_overview(),
            "statistics": self.get_statistics(),
            "storage_overview": self.get_storage_overview(),
            "savings": self.get_savings(),
            "equipment_status": self.get_equipment_status(),
            "errors": self.get_errors(),
            "equipment_list": self.get_equipment_list(),
        }
        if self.equ_sn:
            tasks["grid_chart"] = self.get_grid_chart()

        results: dict[str, Any] = {}
        for key, coro in tasks.items():
            try:
                results[key] = await coro
            except RenacApiError as err:
                results[key] = {"error": str(err)}
        return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_stations(data: Any) -> list[dict[str, Any]]:
    """Best-effort extraction of station list from an arbitrary API response."""
    items: list[Any] = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        for key in ("data", "rows", "list", "records", "stations", "stationList"):
            if isinstance(data.get(key), list):
                items = data[key]
                break

    stations = []
    for item in items:
        if not isinstance(item, dict):
            continue
        sid = next((item[k] for k in _STATION_ID_KEYS if k in item), None)
        name = next((item[k] for k in _STATION_NAME_KEYS if k in item), None)
        uid = next((item[k] for k in _USER_ID_KEYS if k in item), None)
        if sid:
            stations.append({
                "station_id": str(sid),
                "name": name,
                "user_id": str(uid) if uid else None,
                "raw": item,
            })
    return stations


def _deep_find(payload: Any, candidates: list[str]) -> Any:
    for candidate in candidates:
        current = payload
        for part in candidate.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                current = None
                break
        if current:
            return current
    if isinstance(payload, dict):
        for value in payload.values():
            found = _deep_find(value, candidates)
            if found:
                return found
    if isinstance(payload, list):
        for item in payload:
            found = _deep_find(item, candidates)
            if found:
                return found
    return None


def _get_client(require_station: bool = True) -> RenacClient:
    """Build a RenacClient from environment variables.

    station_id and user_id are optional when require_station=False
    (used for discovery tools that only need credentials).
    """
    base_url = os.environ.get("RENAC_BASE_URL", "https://sec.bg.renacpower.cn:8084")
    username = os.environ.get("RENAC_USERNAME", "")
    password = os.environ.get("RENAC_PASSWORD", "")
    station_id = os.environ.get("RENAC_STATION_ID", "")
    user_id = os.environ.get("RENAC_USER_ID", "")
    equ_sn = os.environ.get("RENAC_EQU_SN") or None

    missing = [k for k, v in {"RENAC_USERNAME": username, "RENAC_PASSWORD": password}.items() if not v]
    if require_station:
        missing += [k for k, v in {"RENAC_STATION_ID": station_id, "RENAC_USER_ID": user_id}.items() if not v]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return RenacClient(
        base_url=base_url,
        username=username,
        password=password,
        station_id=station_id,
        user_id=user_id,
        equ_sn=equ_sn,
    )


async def _run(coro: Any) -> Any:
    client = _get_client()
    try:
        return await coro(client)
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def fetch_all_data() -> dict[str, Any]:
    """Fetch all available data from the RENAC station in one call.

    Returns station_overview (current power + today/total energy),
    statistics (month/year totals), storage_overview (battery/load breakdown),
    savings (financial + environmental), equipment status, errors, equipment list,
    and (if RENAC_EQU_SN is configured) the grid chart.
    """
    return await _run(lambda c: c.fetch_all())


@mcp.tool()
async def get_station_overview() -> dict[str, Any]:
    """Get real-time station overview: current PV power (W), today's energy (kWh), total lifetime energy (kWh).

    Returns results list where results[0] has: currentPower (W), dayPower (kWh), totalPower (kWh).
    """
    return await _run(lambda c: c.get_station_overview())


@mcp.tool()
async def get_statistics() -> dict[str, Any]:
    """Get energy statistics: month/year/lifetime totals and financial summary.

    Returns results dict with: month_power_total, year_power_total, total_power_gt (kWh),
    total_price, total_month_price, total_year_price, total_day_price (currency),
    co2, so2, fuel, tree (environmental).
    """
    return await _run(lambda c: c.get_statistics())


@mcp.tool()
async def get_battery_status() -> dict[str, Any]:
    """Get battery / storage overview including today and total energy split by source.

    Returns data.today and data.total arrays with DAY_PV_ENERGY, DAY_BAT_CHARGE,
    DAY_BAT_DISCHARGE, DAY_ENERGY_LOAD, METER_FEEDIN_DAY, METER_CONSUM_DAY.
    """
    return await _run(lambda c: c.get_storage_overview())


@mcp.tool()
async def get_savings() -> dict[str, Any]:
    """Get total financial savings and CO2 reduction statistics for the station."""
    return await _run(lambda c: c.get_savings())


@mcp.tool()
async def get_equipment_status() -> dict[str, Any]:
    """Get equipment status overview: how many devices are online, offline, or in fault."""
    return await _run(lambda c: c.get_equipment_status())


@mcp.tool()
async def get_errors(rows: int = 20, offset: int = 0) -> dict[str, Any]:
    """Get today's error list from the station.

    Args:
        rows: Maximum number of errors to return (default 20).
        offset: Pagination offset (default 0).
    """
    return await _run(lambda c: c.get_errors(rows=rows, offset=offset))


@mcp.tool()
async def get_daily_energy(day: str | None = None) -> dict[str, Any]:
    """Get hourly energy production chart for a specific day.

    Args:
        day: Date in YYYY-MM-DD format. Defaults to today.
    """
    return await _run(lambda c: c.get_chart_day(day=day))


@mcp.tool()
async def get_monthly_energy(month: str | None = None) -> dict[str, Any]:
    """Get daily energy production chart for a specific month.

    Args:
        month: Month in YYYY-MM format. Defaults to current month.
    """
    return await _run(lambda c: c.get_chart_month(month=month))


@mcp.tool()
async def get_yearly_energy(year: str | None = None) -> dict[str, Any]:
    """Get monthly energy production chart for a specific year.

    Args:
        year: Year in YYYY format. Defaults to current year.
    """
    return await _run(lambda c: c.get_chart_year(year=year))


@mcp.tool()
async def get_equipment_list(rows: int = 20, offset: int = 0) -> dict[str, Any]:
    """Get list of all equipment (inverters, meters, batteries) registered to the station.

    Args:
        rows: Maximum number of equipment entries to return (default 20).
        offset: Pagination offset (default 0).
    """
    return await _run(lambda c: c.get_equipment_list(rows=rows, offset=offset))


@mcp.tool()
async def get_inverter_detail(equ_sn: str | None = None) -> dict[str, Any]:
    """Get detailed real-time data for a specific inverter.

    Args:
        equ_sn: Inverter serial number. Falls back to RENAC_EQU_SN env var if omitted.
    """
    return await _run(lambda c: c.get_inverter_detail(equ_sn=equ_sn))


@mcp.tool()
async def get_grid_chart(equ_sn: str | None = None) -> dict[str, Any]:
    """Get today's grid power chart for a specific inverter.

    Args:
        equ_sn: Inverter serial number. Falls back to RENAC_EQU_SN env var if omitted.
    """
    return await _run(lambda c: c.get_grid_chart(equ_sn=equ_sn))


@mcp.tool()
async def discover_account() -> dict[str, Any]:
    """Discover station IDs and user ID directly from the API after login.

    Only RENAC_USERNAME and RENAC_PASSWORD are required.
    Returns the login response (which often contains user_id and station list)
    plus the result of probing known station-list endpoints.

    Use this tool to find the values you need to set in RENAC_STATION_ID
    and RENAC_USER_ID — no manual lookup required.
    """
    client = _get_client(require_station=False)
    try:
        return await client.discover_stations()
    finally:
        await client.close()


@mcp.tool()
async def test_connection() -> dict[str, Any]:
    """Test connectivity and authentication with the RENAC API.

    Returns the authenticated token (masked) and station configuration on success.
    """
    client = _get_client()
    try:
        token = await client.login()
        return {
            "status": "ok",
            "token_preview": f"{token[:8]}…" if len(token) > 8 else "***",
            "base_url": client.base_url,
            "station_id": client.station_id,
            "equ_sn_configured": bool(client.equ_sn),
        }
    except Exception as err:
        return {"status": "error", "message": str(err)}
    finally:
        await client.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
