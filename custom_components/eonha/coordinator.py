"""DataUpdateCoordinator for E.ON Next Home Assistant."""
from datetime import datetime, timedelta, timezone
import logging
try:
    from glowmarkt import BrightClient as Glow
except ImportError:
    Glow = None

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
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
        entry: ConfigEntry,
        api: EonNextAPI,
        username: str,
        password: str,
        backfill_days: int = 30,
        target_statistic_id: str | None = None,
        glow_username: str | None = None,
        glow_password: str | None = None,
    ) -> None:
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.api = api
        self.username = username
        self.password = password
        self.backfill_days = backfill_days
        self.target_statistic_id = target_statistic_id
        
        self.glow_username = glow_username
        self.glow_password = glow_password
        self.glow_client = None
        
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

            # Determine fetch window
            # If we have no data yet, it's the first run: fetch backfill window.
            # Otherwise, fetch shorter window (e.g. 7 days) to ensure we catch up on recent misses.
            days_to_fetch = self.backfill_days if not self.data.get("meters") else 2

            for account in account_numbers:
                meters = await self.api.get_meters(account)
                
                for meter in meters:
                    # Fetch consumption data
                    end_date = datetime.now()
                    start_date = end_date - timedelta(days=days_to_fetch)
                    
                    consumption = await self.api.get_consumption_data(
                        account,
                        meter['id'],
                        meter['type'],
                        start_date,
                        end_date
                    )
                    
                    # Sort by date
                    if consumption:
                        consumption.sort(key=lambda x: x['startAt'])

                    # --- GLOWMARKT MERGE START ---
                    if (
                        self.glow_username 
                        and self.glow_password 
                        and meter['type'] == 'electricity' 
                        and Glow is not None
                    ):
                        try:
                             # Determine where to start fetching Glow data from
                             # If we have E.ON data, start from the last point. 
                             # Else start from 2 days ago.
                             glow_start = datetime.now() - timedelta(days=2)
                             if consumption:
                                 last_eon = datetime.fromisoformat(consumption[-1]["startAt"])
                                 # Add 30 mins to avoid overlap
                                 glow_start = last_eon + timedelta(minutes=30)
                                 # Ensure timezone match (naive/aware comparison fix)
                                 if glow_start.tzinfo is None:
                                     glow_start = glow_start.replace(tzinfo=datetime.now().astimezone().tzinfo)

                             glow_data = await self.hass.async_add_executor_job(
                                 self._fetch_glow_data, glow_start
                             )
                             
                             if glow_data:
                                 _LOGGER.debug(f"Merged {len(glow_data)} records from Glowmarkt")
                                 consumption.extend(glow_data)
                                 # Re-sort just in case
                                 consumption.sort(key=lambda x: x['startAt'])
                        except Exception as e:
                            _LOGGER.warning(f"Failed to fetch Glowmarkt data: {e}")
                    # --- GLOWMARKT MERGE END ---

                    meter_entry = {
                        "info": meter,
                        "account": account,
                        "consumption": consumption
                    }
                    all_meter_data.append(meter_entry)

            return {"meters": all_meter_data}

        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    def _fetch_glow_data(self, start_time: datetime) -> list[dict]:
        """Fetch data from Glowmarkt (Sync method to be run in executor)."""
        if not self.glow_client:
            try:
                # Assuming Glow is BrightClient
                self.glow_client = Glow(self.glow_username, self.glow_password)
            except Exception as e:
                 _LOGGER.warning(f"Failed to initialize Glowmarkt client: {e}")
                 return []
        
        # We need to find the right resource. 
        target_resource = None
        
        try:
            # Use get_virtual_entities if available
            if hasattr(self.glow_client, 'get_virtual_entities'):
                entities = self.glow_client.get_virtual_entities()
            elif hasattr(self.glow_client, 'virtual_entities'):
                entities = self.glow_client.virtual_entities
            else:
                 _LOGGER.warning("Glow client missing virtual_entities methods")
                 return []
                 
            for virt in entities:
                # Use get_resources if available
                if hasattr(virt, 'get_resources'):
                    resources = virt.get_resources()
                elif hasattr(virt, 'resources'):
                    resources = virt.resources
                else:
                    continue
                    
                for res in resources:
                    if res.classifier == 'electricity.consumption':
                        target_resource = res
                        break
                if target_resource:
                    break
        except Exception as e:
            _LOGGER.warning(f"Error finding Glow resource: {e}")
            return []
            
        if not target_resource:
            return []

        # Helper to format as YYYY-MM-DDTHH:mm:ss in UTC
        def to_glow_str(dt: datetime) -> str:
            # Convert to aware UTC
            if dt.tzinfo is None:
                dt = dt.astimezone(timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime('%Y-%m-%dT%H:%M:%S')

        end_time = datetime.now(timezone.utc)
        
        # Guard against future start time or start > end
        if start_time > end_time:
            # If start is in future (clock skew?), fetch at least small window or return
            # But let's just clamp it or log it
            _LOGGER.debug(f"Glow start time {start_time} is in future vs {end_time}, adjusting window")
            start_time = end_time - timedelta(hours=24) # Fallback

        str_from = to_glow_str(start_time)
        str_to = to_glow_str(end_time)
        
        url = f"https://api.glowmarkt.com/api/v0-1/resource/{target_resource.id}/readings"
        params = {
            "from": str_from,
            "to": str_to,
            "period": "PT30M",
            "offset": 0,
            "function": "sum",
            "nulls": 0
        }
        
        try:
            # Re-use session from client, but must include auth headers
            headers = {
                "Content-Type": "application/json",
                "applicationId": self.glow_client.application,
                "token": self.glow_client.token
            }
            resp = self.glow_client.session.get(url, headers=headers, params=params)
            
            if resp.status_code != 200:
                _LOGGER.warning(f"Glow API Error: {resp.status_code} {resp.text} | URL: {url} | Params: {params}")
                return []
                
            data = resp.json().get('data', [])
        except Exception as e:
            _LOGGER.warning(f"Failed to fetch Glow readings: {e}")
            return []

        results = []
        if not data:
            return results

        for entry in data:
            # entry: [timestamp, value]
            ts = entry[0]
            val_raw = entry[1]
            
            if val_raw is None:
                continue
                
            # Handle object vs float (though raw JSON usually gives float/int)
            val = float(val_raw)
            
            # ts is unix timestamp
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            
            # Add timezone info (UTC)
            dt_iso = dt.replace(microsecond=0).isoformat()
            
            # EndAt is Start + 30m
            end_dt_iso = (dt + timedelta(minutes=30)).replace(microsecond=0).isoformat()
            
            results.append({
                "startAt": dt_iso,
                "endAt": end_dt_iso,
                "value": val
            })
            
        return results
