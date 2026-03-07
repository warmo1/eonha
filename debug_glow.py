
import asyncio
import os
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
try:
    from glowmarkt import BrightClient as Glow
except ImportError as e:
    print(f"pyglowmarkt not installed (module name might be glowmarkt). Error: {e}")
    sys.exit(1)

load_dotenv()

def main():
    username = os.getenv("GLOW_USERNAME")
    password = os.getenv("GLOW_PASSWORD")

    if not username or not password:
        print("Error: GLOW_USERNAME and GLOW_PASSWORD not found in .env file.")
        print("Please add them to /home/dev/eonha/.env")
        sys.exit(1)

    print(f"Logging in to Glowmarkt as {username}...")
    try:
        glow = Glow(username, password)
        print("Login successful!")
        
        # Find electricity resource
        target_resource = None
        virtual_entities = glow.get_virtual_entities()
        
        for virt in virtual_entities:
            print(f"Checking entity: {virt.name}")
            resources = virt.get_resources()
            for res in resources:
                print(f"  - Resource: {res.name} ({res.classifier})")
                if res.classifier == 'electricity.consumption':
                    target_resource = res
        
        if not target_resource:
            print("No electricity consumption resource found!")
            return

        print(f"\nFetching data for resource: {target_resource.name} ({target_resource.id})")
        
        # Fetch last 4 days to see "recent" history
        end = datetime.now()
        start = end - timedelta(days=4)
        
        print(f"Requesting data: {start} -> {end} (PT30M)")
        
        # Note: catch_up=True might be slow or return different format? 
        # The library's get_readings returns a list of [timestamp, value] usually
        data = target_resource.get_readings(start, end, period='PT30M')
        
        if not data:
            print("No data returned!")
        else:
            print(f"Retrieved {len(data)} records.")
            print("-" * 40)
            print("TimeStamp (Local/UTC?) | Value (kWh)")
            print("-" * 40)
            
            # Print first 5
            for row in data[:5]:
                print(f"{row[0]} | {row[1]}")
            
            if len(data) > 10:
                print("... (skipping) ...")
            
            # Print last 5
            for row in data[-5:]:
                print(f"{row[0]} | {row[1]}")
            print("-" * 40)
            
            # Analyze
            values = [float(x[1].value) for x in data]
            print(f"Min: {min(values)}")
            print(f"Max: {max(values)}")
            print(f"Sum: {sum(values)}")

    except Exception as e:
        print(f"Glowmarkt Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
