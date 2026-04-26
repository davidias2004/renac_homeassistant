from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

import aiohttp


class RenacApiError(Exception):
    """RENAC API error."""


@dataclass
class RenacApiClient:
    session: aiohttp.ClientSession
    base_url: str
    username: str
    password: str
    station_id: str
    user_id: str
    equ_sn: str | None = None

    token: str | None = None

    async def _raw_login(self) -> dict:
        """Login and return the full response payload (useful for discovery)."""
        data = await self._request(
            "POST",
            "/api/user/login",
            json={"login_name": self.username, "pwd": self.password},
            auth_required=False,
        )
        token = self._deep_find(data, ["token", "access_token", "data.token", "data.access_token"])
        if not token:
            raise RenacApiError(f"Login efetuado, mas token não encontrado na resposta: {data}")
        self.token = str(token)
        return data if isinstance(data, dict) else {}

    async def async_login(self) -> str:
        data = await self._raw_login()
        return self.token  # type: ignore[return-value]

    async def async_fetch_all(self) -> dict[str, Any]:
        if not self.token:
            await self.async_login()

        today = date.today().isoformat()
        month = today[:7]
        year = today[:4]

        payloads = {
            "power_flow": self._form("/api/home/station/powerFlow", {"station_id": self.station_id}),
            "storage_overview": self._json("/api/station/storage/overview", {"station_id": self.station_id}),
            "savings": self._json("/api/station/all/savings", {"station_id": self.station_id}),
            "equip_stat": self._json("/api/station/equipStat", {"station_id": self.station_id, "user_id": self.user_id}),
            "errors": self._json("/api/home/errorList2", {
                "user_id": self.user_id,
                "begin_time": today,
                "end_time": today,
                "offset": 0,
                "rows": 5,
                "station_id": self.station_id,
                "status": "0",
            }),
            "chart_day": self._json("/api/station/chart/station", {"time_type": 1, "station_id": self.station_id, "time": today}),
            "chart_month": self._json("/api/station/chart/station", {"time_type": 3, "station_id": self.station_id, "time": month}),
            "chart_year": self._json("/api/station/chart/station", {"time_type": 4, "station_id": self.station_id, "time": year}),
            "equipment_list": self._json("/bg/equList", {
                "user_id": self.user_id,
                "station_id": self.station_id,
                "status": 0,
                "offset": 0,
                "rows": 10,
                "equ_sn": "",
            }),
        }

        if self.equ_sn:
            payloads["inverter_detail"] = self._json("/bg/inv/detail", {
                "equ_sn": self.equ_sn,
                "offset": 0,
                "rows": 10,
                "time": today,
            })
            payloads["grid_chart"] = self._json("/api/inv/gridChart2", {
                "equipSn": self.equ_sn,
                "timeType": 1,
                "time": today,
                "temId": 6,
            })

        results: dict[str, Any] = {}
        for key, request_args in payloads.items():
            try:
                results[key] = await self._request("POST", **request_args)
            except RenacApiError as err:
                if "token" in str(err).lower() or "401" in str(err):
                    await self.async_login()
                    results[key] = await self._request("POST", **request_args)
                else:
                    results[key] = {"error": str(err)}
        return results

    def _json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"path": path, "json": payload}

    def _form(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "path": path,
            "data": payload,
            "headers": {"content-type": "application/x-www-form-urlencoded;charset=UTF-8"},
        }

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
        req_headers = {
            "accept": "application/json, text/plain, */*",
            "Referer": "https://sec.eu.renacpower.com/",
        }
        if json is not None:
            req_headers["content-type"] = "application/json;charset=UTF-8"
        if headers:
            req_headers.update(headers)
        if auth_required:
            if not self.token:
                await self.async_login()
            req_headers["token"] = self.token or ""

        async with self.session.request(method, url, json=json, data=data, headers=req_headers, timeout=aiohttp.ClientTimeout(total=30)) as resp:
            text = await resp.text()
            if resp.status >= 400:
                raise RenacApiError(f"HTTP {resp.status} em {path}: {text[:300]}")
            try:
                payload = await resp.json(content_type=None)
            except Exception as err:
                raise RenacApiError(f"Resposta não JSON em {path}: {text[:300]}") from err

        if isinstance(payload, dict):
            code = payload.get("code") or payload.get("status")
            msg = payload.get("msg") or payload.get("message")
            if code in (401, 403, "401", "403"):
                raise RenacApiError(f"Token inválido/expirado em {path}: {msg or payload}")
        return payload

    @staticmethod
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
                found = RenacApiClient._deep_find(value, candidates)
                if found:
                    return found
        if isinstance(payload, list):
            for item in payload:
                found = RenacApiClient._deep_find(item, candidates)
                if found:
                    return found
        return None
