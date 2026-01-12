"""The E.ON Next Home Assistant integration."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from eonapi.api import EonNextAPI
from .coordinator import EonNextDataUpdateCoordinator
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up E.ON Next Home Assistant from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    api = EonNextAPI()
    try:
        username = entry.data[CONF_USERNAME]
        password = entry.data[CONF_PASSWORD]
        
        # Initial login
        if not await api.login(username, password):
             _LOGGER.error("Failed to login to E.ON Next API")
             return False
        
        coordinator = EonNextDataUpdateCoordinator(hass, api, username, password)
        
        # Fetch initial data so we have something when entities are created
        await coordinator.async_config_entry_first_refresh()

        hass.data[DOMAIN][entry.entry_id] = coordinator

    except Exception as e:
        _LOGGER.error("Error setting up E.ON Next integration: %s", e)
        return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
