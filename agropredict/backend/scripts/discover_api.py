"""Probe the Agmarknet 2.0 internal API endpoints."""
import httpx
import json

BASE = "https://api.agmarknet.gov.in/v1"

headers = {
    "Accept": "application/json",
    "Origin": "https://agmarknet.gov.in",
    "Referer": "https://agmarknet.gov.in/",
}

# 1. Get filters/dropdowns
print("=" * 60)
print("1. Daily price arrival filters:")
try:
    r = httpx.get(f"{BASE}/daily-price-arrival/filters", headers=headers, timeout=30.0)
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"   Keys: {list(data.keys()) if isinstance(data, dict) else 'list'}")
        print(f"   Sample: {json.dumps(data, indent=2)[:1000]}")
except Exception as e:
    print(f"   Error: {e}")

# 2. Try to get states
print("\n" + "=" * 60)
print("2. States:")
try:
    r = httpx.get(f"{BASE}/location/state?page_size=100", headers=headers, timeout=30.0)
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        if isinstance(data, dict) and "results" in data:
            for s in data["results"][:5]:
                print(f"   {s}")
        else:
            print(f"   {json.dumps(data, indent=2)[:500]}")
except Exception as e:
    print(f"   Error: {e}")

# 3. Try commodities
print("\n" + "=" * 60)
print("3. Commodities:")
try:
    r = httpx.get(f"{BASE}/commodities?page_size=500", headers=headers, timeout=30.0)
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        results = data.get("results", data) if isinstance(data, dict) else data
        if isinstance(results, list):
            # Find onion, potato, tomato, tur
            for item in results:
                name = str(item.get("commodity_name", item.get("name", ""))).lower()
                if any(k in name for k in ["onion", "potato", "tomato", "arhar", "tur"]):
                    print(f"   {item}")
except Exception as e:
    print(f"   Error: {e}")

# 4. Try market report
print("\n" + "=" * 60)
print("4. Daily market report:")
try:
    r = httpx.get(
        f"{BASE}/prices-and-arrivals/market-report/daily",
        params={"state_id": "33", "date": "2026-07-15"},
        headers=headers,
        timeout=30.0,
    )
    print(f"   Status: {r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"   Keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
        print(f"   Sample: {json.dumps(data, indent=2)[:1000]}")
    else:
        print(f"   Response: {r.text[:500]}")
except Exception as e:
    print(f"   Error: {e}")
