"""
AgroPredict - Agmarknet Web Scraper (Primary Data Source)

The data.gov.in API (resource 9ef84268-d588-465a-a308-a864a43d0070)
is extremely unreliable and frequently times out. This module
scrapes the Agmarknet 2.0 portal directly as the primary data source.

It uses httpx to POST to the Agmarknet reports endpoint and
parses the HTML table response.

Endpoint: https://agmarknet.gov.in/SearchCmmMkt.aspx
"""

import logging
import re
import time
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.mysql import insert as mysql_insert
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.ingestion.mandi_geocoding import (
    COMMODITY_API_NAME_MAP,
    MANDI_API_NAME_MAP,
)
from app.models.commodity import Commodity, Mandi, PriceObservation

logger = logging.getLogger(__name__)

AGMARKNET_URL = "https://agmarknet.gov.in"
SEARCH_URL = f"{AGMARKNET_URL}/SearchCmmMkt.aspx"

# Commodity codes used in the Agmarknet dropdown
# These were determined by inspecting the Agmarknet portal
COMMODITY_CODES = {
    "onion": "23",        # Onion
    "potato": "24",       # Potato
    "tomato": "78",       # Tomato
    "tur_dal": "42",      # Arhar (Tur/Red Gram)(Whole)
}

# State code for Tamil Nadu in Agmarknet
STATE_CODE_TN = "TN"


def _parse_price(price_str: str) -> Optional[float]:
    """Parse price from HTML table cell."""
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.]', '', price_str.strip())
    if not cleaned:
        return None
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None


def _format_date_agmarknet(d: date) -> str:
    """Format date for Agmarknet form submission: DD-Mon-YYYY."""
    return d.strftime("%d-%b-%Y")


def fetch_prices_from_agmarknet(
    commodity_name: str,
    state: str,
    from_date: date,
    to_date: date,
) -> list[dict]:
    """
    Fetch commodity prices from the Agmarknet portal.

    This function makes an HTTP request to the Agmarknet search
    endpoint and parses the results. Since the portal uses ASP.NET
    postback, we need to first GET the page to obtain viewstate tokens,
    then POST with our search parameters.

    Returns a list of dicts with keys:
        market, district, commodity, variety, grade,
        min_price, max_price, modal_price, arrival_date
    """
    results = []

    try:
        with httpx.Client(timeout=60.0, follow_redirects=True) as client:
            # Step 1: GET the search page to get ASP.NET tokens
            logger.debug("Fetching Agmarknet search page...")
            page_response = client.get(SEARCH_URL)
            if page_response.status_code != 200:
                logger.error(
                    f"Failed to load Agmarknet search page: {page_response.status_code}"
                )
                return results

            # Parse __VIEWSTATE and __EVENTVALIDATION from the page
            page_html = page_response.text
            viewstate = _extract_hidden_field(page_html, "__VIEWSTATE")
            event_validation = _extract_hidden_field(
                page_html, "__EVENTVALIDATION"
            )
            viewstate_gen = _extract_hidden_field(
                page_html, "__VIEWSTATEGENERATOR"
            )

            if not viewstate:
                logger.warning("Could not extract __VIEWSTATE from page")
                # Try direct API-style request instead
                return _try_direct_api(commodity_name, state, from_date, to_date)

            # Step 2: POST with search parameters
            form_data = {
                "__VIEWSTATE": viewstate,
                "__EVENTVALIDATION": event_validation or "",
                "__VIEWSTATEGENERATOR": viewstate_gen or "",
                "ctl00$ContentPlaceHolder1$ddlArrivalDate": _format_date_agmarknet(from_date),
                "ctl00$ContentPlaceHolder1$ddlArrivalDateTo": _format_date_agmarknet(to_date),
                "ctl00$ContentPlaceHolder1$ddlCommodity": commodity_name,
                "ctl00$ContentPlaceHolder1$ddlState": state,
                "ctl00$ContentPlaceHolder1$btnGo": "Go",
            }

            time.sleep(1)  # Be polite to the server

            search_response = client.post(
                SEARCH_URL,
                data=form_data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": SEARCH_URL,
                },
            )

            if search_response.status_code != 200:
                logger.error(
                    f"Search request failed: {search_response.status_code}"
                )
                return results

            # Parse the results table
            results = _parse_results_table(search_response.text)
            logger.info(f"  Parsed {len(results)} records from Agmarknet")

    except Exception as e:
        logger.error(f"Agmarknet scraping failed: {e}")
        # Fall back to direct API
        return _try_direct_api(commodity_name, state, from_date, to_date)

    return results


def _extract_hidden_field(html: str, field_name: str) -> Optional[str]:
    """Extract a hidden form field value from HTML."""
    pattern = rf'id="{field_name}"\s+value="([^"]*)"'
    match = re.search(pattern, html)
    if match:
        return match.group(1)
    # Try alternate pattern
    pattern = rf'name="{field_name}"\s+value="([^"]*)"'
    match = re.search(pattern, html)
    return match.group(1) if match else None


def _parse_results_table(html: str) -> list[dict]:
    """Parse the price results table from the Agmarknet response HTML."""
    results = []

    # Find all table rows that contain price data
    # The results table typically has rows with market, commodity, variety,
    # grade, min_price, max_price, modal_price, arrival_date
    row_pattern = re.compile(
        r'<tr[^>]*>\s*'
        r'<td[^>]*>(\d+)</td>\s*'       # Sl No
        r'<td[^>]*>([^<]*)</td>\s*'     # District
        r'<td[^>]*>([^<]*)</td>\s*'     # Market
        r'<td[^>]*>([^<]*)</td>\s*'     # Commodity
        r'<td[^>]*>([^<]*)</td>\s*'     # Variety
        r'<td[^>]*>([^<]*)</td>\s*'     # Grade
        r'<td[^>]*>([^<]*)</td>\s*'     # Min Price
        r'<td[^>]*>([^<]*)</td>\s*'     # Max Price
        r'<td[^>]*>([^<]*)</td>\s*'     # Modal Price
        r'<td[^>]*>([^<]*)</td>\s*'     # Price Date
        r'</tr>',
        re.DOTALL | re.IGNORECASE,
    )

    for match in row_pattern.finditer(html):
        try:
            date_str = match.group(10).strip()
            arrival_date = None
            for fmt in ("%d %b %Y", "%d/%m/%Y", "%d-%b-%Y", "%Y-%m-%d"):
                try:
                    arrival_date = datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    continue

            if arrival_date is None:
                continue

            results.append({
                "district": match.group(2).strip(),
                "market": match.group(3).strip(),
                "commodity": match.group(4).strip(),
                "variety": match.group(5).strip(),
                "grade": match.group(6).strip(),
                "min_price": _parse_price(match.group(7)),
                "max_price": _parse_price(match.group(8)),
                "modal_price": _parse_price(match.group(9)),
                "arrival_date": arrival_date,
            })
        except Exception as e:
            logger.debug(f"Failed to parse row: {e}")
            continue

    return results


def _try_direct_api(
    commodity_name: str,
    state: str,
    from_date: date,
    to_date: date,
) -> list[dict]:
    """
    Fallback: try the data.gov.in API with very long timeout.
    This may or may not work depending on API availability.
    """
    from app.core.config import get_settings
    settings = get_settings()
    api_key = settings.DATA_GOV_IN_API_KEY

    if not api_key or api_key == "your_api_key_here":
        return []

    RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
    BASE_URL = f"https://api.data.gov.in/resource/{RESOURCE_ID}"

    results = []
    offset = 0

    while True:
        params = {
            "api-key": api_key,
            "format": "json",
            "limit": 1000,
            "offset": offset,
            "filters[State]": state,
            "filters[Commodity]": commodity_name,
        }

        try:
            response = httpx.get(BASE_URL, params=params, timeout=120.0)
            response.raise_for_status()
            data = response.json()
        except Exception as e:
            logger.warning(f"data.gov.in API fallback failed: {e}")
            break

        records = data.get("records", [])
        if not records:
            break

        for record in records:
            date_str = record.get("Arrival_Date", "")
            arrival_date = None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"):
                try:
                    arrival_date = datetime.strptime(date_str.strip(), fmt).date()
                    break
                except (ValueError, AttributeError):
                    continue

            if arrival_date and from_date <= arrival_date <= to_date:
                results.append({
                    "district": record.get("District", ""),
                    "market": record.get("Market", ""),
                    "commodity": record.get("Commodity", ""),
                    "variety": record.get("Variety", ""),
                    "min_price": _parse_price(str(record.get("Min_x0020_Price", "") or record.get("Min Price", ""))),
                    "max_price": _parse_price(str(record.get("Max_x0020_Price", "") or record.get("Max Price", ""))),
                    "modal_price": _parse_price(str(record.get("Modal_x0020_Price", "") or record.get("Modal Price", ""))),
                    "arrival_date": arrival_date,
                })

        total = int(data.get("total", 0))
        offset += 1000
        if offset >= total:
            break

        time.sleep(2)  # Rate limit

    return results


def bulk_pull_agmarknet(
    db: Session,
    commodity_slugs: list[str],
    start_date: date,
    end_date: date,
) -> dict:
    """
    Pull historical commodity prices. Tries Agmarknet web portal first,
    falls back to data.gov.in API.

    Chunks requests by month to avoid overloading the server.
    """
    results_summary = {}

    for slug in commodity_slugs:
        api_name = COMMODITY_API_NAME_MAP.get(slug)
        if not api_name:
            logger.warning(f"No API mapping for slug: {slug}")
            continue

        commodity = db.execute(
            select(Commodity).where(Commodity.slug == slug)
        ).scalar_one_or_none()
        if not commodity:
            logger.warning(f"Commodity '{slug}' not in DB. Skipping.")
            continue

        total_inserted = 0

        # Chunk by month to keep request sizes manageable
        current_start = start_date
        while current_start <= end_date:
            current_end = min(
                date(
                    current_start.year + (current_start.month // 12),
                    (current_start.month % 12) + 1,
                    1,
                ) - timedelta(days=1),
                end_date,
            )

            logger.info(
                f"Pulling {slug} ({current_start} to {current_end})..."
            )

            # Fetch from portal/API
            records = fetch_prices_from_agmarknet(
                commodity_name=api_name,
                state="Tamil Nadu",
                from_date=current_start,
                to_date=current_end,
            )

            # Insert records
            for record in records:
                market_name = record.get("market", "")
                # Find matching mandi
                mandi = None
                for mandi_key in MANDI_API_NAME_MAP:
                    if mandi_key.lower() in market_name.lower():
                        mandi = db.execute(
                            select(Mandi).where(Mandi.name == mandi_key)
                        ).scalar_one_or_none()
                        break

                if not mandi:
                    continue

                if record.get("modal_price") is None and record.get("min_price") is None:
                    continue

                stmt = mysql_insert(PriceObservation).values(
                    commodity_id=commodity.id,
                    mandi_id=mandi.id,
                    date=record["arrival_date"],
                    min_price=record.get("min_price"),
                    max_price=record.get("max_price"),
                    modal_price=record.get("modal_price"),
                    arrival_qty=None,
                )
                stmt = stmt.on_duplicate_key_update(
                    min_price=stmt.inserted.min_price,
                    max_price=stmt.inserted.max_price,
                    modal_price=stmt.inserted.modal_price,
                )
                db.execute(stmt)
                total_inserted += 1

            db.commit()

            current_start = current_end + timedelta(days=1)
            time.sleep(2)  # Rate limit between monthly chunks

        results_summary[slug] = total_inserted
        logger.info(f"[{slug}] Total inserted/updated: {total_inserted}")

    return results_summary
