"""
Live diagnostic test for E.ON Next API.
Runs through each API call step and reports what's happening.
"""
import asyncio
import os
import sys
import json
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'custom_components', 'eonha'))
from eon_api import EonNextAPI


async def diagnose():
    load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))
    username = os.getenv("EON_USERNAME")
    password = os.getenv("EON_PASSWORD")

    if not username or not password:
        print("ERROR: EON_USERNAME / EON_PASSWORD not set in .env")
        return

    api = EonNextAPI()

    # Step 1: Login
    print("=" * 60)
    print("STEP 1: Login")
    print("=" * 60)
    try:
        ok = await api.login(username, password)
        print(f"  Login result: {ok}")
        print(f"  Token valid: {api._is_token_valid()}")
        print(f"  Token expires: {api.token_expires}")
        if api.token_expires:
            exp_dt = datetime.fromtimestamp(api.token_expires, tz=timezone.utc)
            print(f"  Token expires at: {exp_dt.isoformat()}")
    except Exception as e:
        print(f"  LOGIN FAILED: {e}")
        return

    # Step 2: Get account numbers
    print("\n" + "=" * 60)
    print("STEP 2: Get Account Numbers")
    print("=" * 60)
    try:
        accounts = await api.get_account_numbers()
        print(f"  Accounts: {accounts}")
    except Exception as e:
        print(f"  GET ACCOUNTS FAILED: {e}")
        return

    # Step 3: Get meters
    print("\n" + "=" * 60)
    print("STEP 3: Get Meters")
    print("=" * 60)
    all_meters = []
    for acc in accounts:
        try:
            meters = await api.get_meters(acc)
            print(f"  Account {acc}: {len(meters)} meters")
            for m in meters:
                print(f"    - {m['type']}: serial={m['serial']}, id={m['id']}")
            all_meters.extend([(acc, m) for m in meters])
        except Exception as e:
            print(f"  GET METERS FAILED for {acc}: {e}")

    if not all_meters:
        print("  No meters found at all!")
        return

    # Step 4: Try consumption for each meter (short window: 2 days)
    print("\n" + "=" * 60)
    print("STEP 4: Get Consumption Data (last 7 days)")
    print("=" * 60)
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    print(f"  Window: {start_date.isoformat()} -> {end_date.isoformat()}")

    for acc, meter in all_meters:
        print(f"\n  --- Meter: {meter['serial']} ({meter['type']}) ---")
        try:
            data = await api.get_consumption_data(
                acc, meter['id'], meter['type'], start_date, end_date
            )
            print(f"  Records returned: {len(data)}")
            if data:
                print(f"  First: {data[0]}")
                print(f"  Last:  {data[-1]}")
            else:
                print("  NO DATA - trying raw query to see response...")
                await _raw_consumption_test(api, acc, meter, start_date)
        except Exception as e:
            print(f"  CONSUMPTION FAILED: {e}")
            await _raw_consumption_test(api, acc, meter, start_date)


async def _raw_consumption_test(api, acc, meter, start_date):
    """Send a raw query and dump the full response to diagnose the issue."""
    import httpx

    start_str = start_date.strftime("%Y-%m-%dT%H:%M:%S+00:00")
    meter_type = meter['type']

    if meter_type == "electricity":
        query = """
        query getElectricityConsumption($accountNumber: String!, $startDate: DateTime!, $after: String) {
            account(accountNumber: $accountNumber) {
                electricityAgreements(active: true) {
                    meterPoint {
                        meters(includeInactive: false) {
                            id
                            consumption(
                                startAt: $startDate
                                grouping: HALF_HOUR
                                timezone: "Europe/London"
                                first: 100
                                after: $after
                            ) {
                                edges {
                                    node { startAt endAt value }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
            }
        }
        """
    else:
        query = """
        query getGasConsumption($accountNumber: String!, $startDate: DateTime!, $after: String) {
            account(accountNumber: $accountNumber) {
                gasAgreements(active: true) {
                    meterPoint {
                        meters(includeInactive: false) {
                            id
                            consumption(
                                startAt: $startDate
                                grouping: HALF_HOUR
                                timezone: "Europe/London"
                                first: 100
                                after: $after
                            ) {
                                edges {
                                    node { startAt endAt value }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
            }
        }
        """

    op = "getElectricityConsumption" if meter_type == "electricity" else "getGasConsumption"
    variables = {"accountNumber": acc, "startDate": start_str}

    headers = {"authorization": f"JWT {api.auth_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            api.base_url,
            json={"operationName": op, "variables": variables, "query": query},
            headers=headers,
            timeout=30.0,
        )
    print(f"  RAW status: {resp.status_code}")
    body = resp.json()
    print(f"  RAW response (truncated):")
    print(f"  {json.dumps(body, indent=2)[:2000]}")

    # Also try without active filter
    print("\n  --- Retrying WITHOUT active: true filter ---")
    if meter_type == "electricity":
        query2 = """
        query testElec($accountNumber: String!, $startDate: DateTime!) {
            account(accountNumber: $accountNumber) {
                electricityAgreements {
                    meterPoint {
                        meters(includeInactive: false) {
                            id
                            consumption(
                                startAt: $startDate
                                grouping: HALF_HOUR
                                timezone: "Europe/London"
                                first: 10
                            ) {
                                edges {
                                    node { startAt endAt value }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
            }
        }
        """
    else:
        query2 = """
        query testGas($accountNumber: String!, $startDate: DateTime!) {
            account(accountNumber: $accountNumber) {
                gasAgreements {
                    meterPoint {
                        meters(includeInactive: false) {
                            id
                            consumption(
                                startAt: $startDate
                                grouping: HALF_HOUR
                                timezone: "Europe/London"
                                first: 10
                            ) {
                                edges {
                                    node { startAt endAt value }
                                }
                                pageInfo { hasNextPage endCursor }
                            }
                        }
                    }
                }
            }
        }
        """

    op2 = "testElec" if meter_type == "electricity" else "testGas"
    variables2 = {"accountNumber": acc, "startDate": start_str}

    async with httpx.AsyncClient() as client:
        resp2 = await client.post(
            api.base_url,
            json={"operationName": op2, "variables": variables2, "query": query2},
            headers=headers,
            timeout=30.0,
        )
    body2 = resp2.json()
    print(f"  WITHOUT active filter status: {resp2.status_code}")
    print(f"  WITHOUT active filter response:")
    print(f"  {json.dumps(body2, indent=2)[:2000]}")


if __name__ == "__main__":
    asyncio.run(diagnose())
