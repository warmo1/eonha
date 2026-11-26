# <img src="https://raw.githubusercontent.com/warmo1/eonha/main/images/logo.png" width="50" height="50" alt="E.ON Next Logo"> E.ON Home Assistant Integration

![Version](https://img.shields.io/badge/version-v1.3.0-blue)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

This project aims to integrate E.ON Next API data into Home Assistant.
It currently includes the `eonapi` library and scripts to verify connection.

## Setup

1.  Create a virtual environment:
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
2.  Install dependencies:
    ```bash
    pip install -e ./eonapi
    pip install pytest pytest-asyncio
    ```

## Testing

Run unit tests (no credentials needed):
```bash
pytest tests/
```

Run connection test (requires an API key, see below):
```bash
export EON_API_KEY="sk_live_..."
python check_connection.py
```

## Structure
- `eonapi/`: Submodule containing the API client library.
- `tests/`: Unit tests.
- `check_connection.py`: Script to verify API access.

## Authentication (API key)

Since October 2026 E.ON Next signs customers in through Auth0, and the Kraken
API no longer accepts email/password (`Field 'email' is not defined by type
'ObtainJSONWebTokenInput'`). The integration authenticates with the account's
`sk_live_...` API key instead.

E.ON allows **one live key per account** and shows it only once - store it in
a password manager. Creating a new one immediately invalidates the old one in
every app that uses it.

To create a key: sign in at https://www.eonnext.com, then exchange the Auth0
ID token (in the page's `localStorage`, key prefix `@@auth0spajs@@`) for a key
with the Kraken mutation `regenerateSecretKey { key }` (send the token as
`Authorization: Bearer <id_token>`). Check `viewer { liveSecretKey }` first so
you don't replace an existing key. The
[savagelands-net helper](https://github.com/savagelands-net/homeassistant-eon-next#getting-an-api-key)
automates this.

Add the key in **Settings > Devices & services > E.ON Next > Configure >
api_key**. Existing entries keep their entities and history.

## Energy dashboard

The integration imports hourly external statistics (E.ON data arrives 3-5
days late, so live entity states would land in the wrong hours):

| Statistic | Unit |
|---|---|
| `eonha:eon_next_<serial>_electricity_total` / `_peak` / `_offpeak` | kWh |
| `eonha:eon_next_<serial>_electricity_total_cost` / `_peak_cost` / `_offpeak_cost` | GBP |
| `eonha:eon_next_<serial>_gas_total` (+ `_total_cost` if a gas rate is set) | kWh / GBP |

Add either `_total`, or `_peak` + `_offpeak` (never all three) as grid
consumption. Static prices don't work with external statistics in HA core
(home-assistant/core#108551), so use "Use an entity tracking the total costs"
with the matching `_cost` statistic. Rates and the off-peak window
(00:00-06:00) are set in `custom_components/eonha/energy_model.py`.

Do **not** use the `sensor.e_on_next_*` Total / Peak / Off Peak entities in
the Energy dashboard. They sum a rolling fetch window and are informational
only; since 1.3.1 they have no state class so they can't be selected.

## Installation
See [INSTALL.md](INSTALL.md) for installation instructions.
