# Changelog

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
