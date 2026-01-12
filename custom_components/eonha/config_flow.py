"""Config flow for E.ON Next Home Assistant integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from eonapi.api import EonNextAPI

from .const import DOMAIN, CONF_BACKFILL_DAYS, CONF_TARGET_STATISTIC_ID, CONF_GLOW_USERNAME, CONF_GLOW_PASSWORD

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_BACKFILL_DAYS, default=90): int,  # Default increased to 90 as discussed
        vol.Optional(CONF_TARGET_STATISTIC_ID): str,
        vol.Optional(CONF_GLOW_USERNAME): str,
        vol.Optional(CONF_GLOW_PASSWORD): str,
    }
)

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E.ON Next Home Assistant."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api = EonNextAPI()
            try:
                success = await api.login(user_input[CONF_USERNAME], user_input[CONF_PASSWORD])
                if success:
                    return self.async_create_entry(
                        title=user_input[CONF_USERNAME], data=user_input
                    )
                else:
                    errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_BACKFILL_DAYS,
                        default=self.config_entry.options.get(
                            CONF_BACKFILL_DAYS, 
                            self.config_entry.data.get(CONF_BACKFILL_DAYS, 90)
                        ),
                    ): int,
                    vol.Optional(
                        CONF_TARGET_STATISTIC_ID,
                        default=self.config_entry.options.get(
                            CONF_TARGET_STATISTIC_ID,
                            self.config_entry.data.get(CONF_TARGET_STATISTIC_ID, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_GLOW_USERNAME,
                        default=self.config_entry.options.get(
                            CONF_GLOW_USERNAME,
                            self.config_entry.data.get(CONF_GLOW_USERNAME, "")
                        ),
                    ): str,
                    vol.Optional(
                        CONF_GLOW_PASSWORD,
                        default=self.config_entry.options.get(
                            CONF_GLOW_PASSWORD,
                            self.config_entry.data.get(CONF_GLOW_PASSWORD, "")
                        ),
                    ): str,
                }
            ),
        )
