
import asyncio
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
from eonapi.api import EonNextAPI

load_dotenv()

async def main():
    username = os.getenv("EON_USERNAME")
    password = os.getenv("EON_PASSWORD")

    if not username or not password:
        print("Please set EON_USERNAME and EON_PASSWORD environment variables.")
        sys.exit(1)

    print(f"Logging in as {username}...")
    api = EonNextAPI()
    
    try:
        if await api.login(username, password):
            print("Login successful!")
        else:
            print("Login failed.")
            sys.exit(1)
    except Exception as e:
        print(f"Login error: {e}")
        sys.exit(1)

    try:
        accounts = await api.get_account_numbers()
        print(f"Found accounts: {accounts}")

        for account in accounts:
            print(f"Fetching meters for account {account}...")
            meters = await api.get_meters(account)
            for meter in meters:
                print(f"  - ({meter['type']}) {meter['serial']} (ID: {meter['id']})")
                
                # Fetch extensive data
                start_date = datetime.now() - timedelta(days=7)
                end_date = datetime.now()
                
                print(f"    Fetching consumption from {start_date.date()} to {end_date.date()}...")
                data = await api.get_consumption_data(
                    account, 
                    meter['id'], 
                    meter['type'], 
                    start_date, 
                    end_date
                )
                print(f"    Retrieved {len(data)} records.")

    except Exception as e:
        print(f"Error fetching data: {e}")

if __name__ == "__main__":
    asyncio.run(main())
