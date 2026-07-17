"""
Test pulling historical data for the selected mandis/commodities directly from data.gov.in
to see if explicit filters avoid timeouts.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
import json
from app.core.config import get_settings
from app.ingestion.mandi_geocoding import MANDI_API_NAME_MAP, COMMODITY_API_NAME_MAP

settings = get_settings()
api_key = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"
RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

headers = {
    "Accept": "application/json",
}

print(f"API Key: {api_key[:10]}...")

def test_pull():
    mandi_info = MANDI_API_NAME_MAP["Sooramangalam"]
    commodity_name = COMMODITY_API_NAME_MAP["onion"]
    
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": 100,
        "filters[state.keyword]": "Tamil Nadu",
        "filters[district]": mandi_info["district"],
        "filters[market]": mandi_info["market"],
        "filters[commodity]": commodity_name,
    }
    
    print(f"Querying for {commodity_name} in {mandi_info['market']}...")
    try:
        r = httpx.get(BASE_URL, params=params, headers=headers, timeout=60.0)
        print(f"Status Code: {r.status_code}")
        if r.status_code == 200:
            res = r.json()
            records = res.get("records", [])
            print(f"Success! Total records found: {res.get('total', 0)}, page records: {len(records)}")
            if records:
                print("Sample record:")
                print(json.dumps(records[0], indent=2))
        else:
            print(f"Response: {r.text[:500]}")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_pull()
