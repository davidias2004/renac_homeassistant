from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RenacApiClient, RenacApiError
from .const import CONF_BASE_URL, CONF_EQU_SN, CONF_STATION_ID, CONF_USER_ID, DEFAULT_BASE_URL, DOMAIN


class RenacPowerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = RenacApiClient(
                session=session,
                base_url=user_input[CONF_BASE_URL],
                username=user_input[CONF_USERNAME],
                password=user_input[CONF_PASSWORD],
                station_id=str(user_input[CONF_STATION_ID]),
                user_id=str(user_input[CONF_USER_ID]),
                equ_sn=user_input.get(CONF_EQU_SN) or None,
            )
            try:
                await client.async_login()
            except RenacApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(f"{user_input[CONF_USER_ID]}_{user_input[CONF_STATION_ID]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=f"RENAC {user_input[CONF_STATION_ID]}", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL): str,
            vol.Required(CONF_USERNAME): str,
            vol.Required(CONF_PASSWORD): str,
            vol.Required(CONF_USER_ID): str,
            vol.Required(CONF_STATION_ID): str,
            vol.Optional(CONF_EQU_SN, default=""): str,
        })

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
