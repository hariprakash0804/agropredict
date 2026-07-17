"""
AgroPredict - Mandi Geocoding Seed Data

Static mapping of mandi names to approximate lat/long coordinates.
These coordinates are used for Open-Meteo weather API queries.

Updated to focus on the Salem district where the user provided historical data:
1. Sooramangalam (Salem)
2. Ammapet (Salem)
3. Thathakapatti (Salem)
"""

# Mandi seed data: name, state, district, latitude, longitude
MANDI_SEED_DATA = [
    {
        "name": "Sooramangalam",
        "state": "Tamil Nadu",
        "district": "Salem",
        "latitude": 11.6550,
        "longitude": 78.1480,
    },
    {
        "name": "Ammapet",
        "state": "Tamil Nadu",
        "district": "Salem",
        "latitude": 11.6578,
        "longitude": 78.1884,
    },
    {
        "name": "Thathakapatti",
        "state": "Tamil Nadu",
        "district": "Salem",
        "latitude": 11.6372,
        "longitude": 78.1578,
    },
]

# Commodity seed data: name, slug
COMMODITY_SEED_DATA = [
    {"name": "Onion", "slug": "onion"},
    {"name": "Potato", "slug": "potato"},
    {"name": "Tomato", "slug": "tomato"},
    {"name": "Tur Dal", "slug": "tur_dal"},
]

# Mapping of our commodity slugs to data.gov.in / CSV commodity names
COMMODITY_API_NAME_MAP = {
    "onion": "Onion",
    "potato": "Potato",
    "tomato": "Tomato",
    "tur_dal": "Arhar (Tur/Red Gram)(Whole)",
}

# Mapping of our mandi names to their exact strings in the CSV
MANDI_API_NAME_MAP = {
    "Sooramangalam": {
        "district": "Salem",
        "market": "Sooramangalam(Uzhavar Sandhai )",
    },
    "Ammapet": {
        "district": "Salem",
        "market": "Ammapet(Uzhavar Sandhai )",
    },
    "Thathakapatti": {
        "district": "Salem",
        "market": "Thathakapatti(Uzhavar Sandhai )",
    },
}
