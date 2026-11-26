# Changelog

## 1.3.1 - 2026-11-26
- **Fix inflated Energy dashboard usage/cost:** the Total / Peak / Off Peak
  sensors no longer have a state class or `last_reset`. Their value is a
  rolling fetch window that restarts on every HA restart; each restart moved
  `last_reset`, so the recorder re-counted the whole window (~90 days) as
  new consumption. They are now informational only and can't be selected in
  the Energy dashboard; use the `eonha:*` statistics instead.
- After updating, HA raises a "no longer has a state class" repair for these
  sensors: choose to delete their statistics to clear the inflated history.
- New `window_start` attribute on those sensors.

## 1.3.0 - 2026-10-25
- **Auth:** log in with the account `sk_live_` API key. E.ON Next moved
  sign-in to Auth0 (~16 Oct 2026) and the Kraken API dropped email/password.
  New `api_key` field in Configure; existing entries keep entities/history.
- **Security:** credentials are redacted from GraphQL errors (Kraken echoed
  the plain-text password into the HA setup error and logs).
- `check_connection.py` uses the integration's client and `EON_API_KEY`.

## 1.2.x - 2026-06
- Energy dashboard statistics fixed: external statistics use valid
  `eonha:` IDs (previously rejected, so nothing was imported).
- Import runs on startup, not only on the next hourly refresh.
- Self-healing imports: inconsistent sums trigger a clean rebuild, which
  prevents negative usage bars.
- E.ON / Glowmarkt records are deduplicated by instant, not timestamp string.
- GBP cost statistics (`_peak_cost`, `_offpeak_cost`, `_total_cost`), since
  HA core can't apply prices to external statistics.
- Off-peak window 00:00-06:00 (E.ON Next Drive).
- Setup retries on transient failures (`ConfigEntryNotReady`).
