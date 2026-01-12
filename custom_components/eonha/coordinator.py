"""DataUpdateCoordinator for E.ON Next Home Assistant."""
from datetime import datetime, timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from eonapi.api import EonNextAPI
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(minutes=60)

class EonNextDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching E.ON Next data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: EonNextAPI,
        username: str,
        password: str,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.username = username
        self.password = password
        self.data = {"meters": []}
        self.known_meters = set()

    async def _async_update_data(self):
        """Fetch data from API endpoint."""
        try:
            # Ensure valid session
            if not self.api._is_token_valid():
                _LOGGER.debug("Token expired, re-logging in")
                if not await self.api.login(self.username, self.password):
                    raise UpdateFailed("Failed to re-authenticate with E.ON Next")

            # Discover accounts if we haven't or just to be safe (it's cheap)
            account_numbers = await self.api.get_account_numbers()
            
            all_meter_data = []

            for account in account_numbers:
                meters = await self.api.get_meters(account)
                
                for meter in meters:
                    # Fetch latest consumption
                    # We fetch last 7 days to ensure we get something, 
                    # but we are mainly interested in the latest.
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=7)
                    
                    consumption = await self.api.get_consumption_data(
                        account,
                        meter['id'],
                        meter['type'],
                        start_date,
                        end_date
                    )

                    latest_reading = None
                    if consumption:
                        # Assuming the API returns sorted or we sort it?
                        # The code in api.py appends, usually efficient. 
                        # Let's sort by date to be sure.
                        consumption.sort(key=lambda x: x['startAt'], reverse=True)
                        latest_reading = consumption[0]

                    meter_entry = {
                        "info": meter,
                        "account": account,
                        "latest_reading": latest_reading
                    }
                    all_meter_data.append(meter_entry)

            return {"meters": all_meter_data}

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
