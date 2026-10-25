"""Verify E.ON Next API access using the integration's own client.

Usage:
    export EON_API_KEY="sk_live_..."
    python check_connection.py
"""
import asyncio
import importlib.util
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

_SPEC = importlib.util.spec_from_file_location(
    "eonha_eon_api",
    Path(__file__).resolve().parent / "custom_components" / "eonha" / "eon_api.py",
)
_MOD = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MOD)
EonNextAPI = _MOD.EonNextAPI


async def main() -> None:
    api_key = os.getenv("EON_API_KEY")
    if not api_key:
        print("Please set the EON_API_KEY environment variable (sk_live_...).")
        sys.exit(1)

    api = EonNextAPI(api_key=api_key)
    try:
        await api.login()
        print("Login successful!")
    except Exception as err:
        print(f"Login error: {err}")
        sys.exit(1)

    accounts = await api.get_account_numbers()
    print(f"Found accounts: {accounts}")
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=7)
    for account in accounts:
        for meter in await api.get_meters(account):
            print(f"  - ({meter['type']}) {meter['serial']} (ID: {meter['id']})")
            data = await api.get_consumption_data(
                account, meter["id"], meter["type"], start, end
            )
            if data:
                print(f"    {len(data)} half-hours, latest {data[-1]['startAt']}")
            else:
                print("    no consumption in the last 7 days")


if __name__ == "__main__":
    asyncio.run(main())
