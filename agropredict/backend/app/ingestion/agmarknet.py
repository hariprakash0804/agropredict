"""
AgroPredict - AGMARKNET Data Ingestion (via data.gov.in API)

Pulls commodity price data from the data.gov.in Open Government Data API.
Resource: "Current Daily Price of Various Commodities from Various Markets (Mandi)"
Resource ID: 9ef84268-d588-465a-a308-a864a43d0070

API returns fields: State, District, Market, Commodity, Variety,
                    Min_x0020_Price, Max_x0020_Price, Modal_x0020_Price,
                    Arrival_Date
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional

import httpx
# pyrefly: ignore [missing-import]
from sqlalchemy import select, text
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.mysql import insert as mysql_insert
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.ingestion.mandi_geocoding import (
    COMMODITY_API_NAME_MAP,
    MANDI_API_NAME_MAP,
)
from app.models.commodity import Commodity, Mandi, PriceObservation

logger = logging.getLogger(__name__)

DAILY_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
HISTORICAL_RESOURCE_ID = "35985678-0d79-46b4-9ed6-6f13308a1d24"


def _get_api_key() -> str:
    """Get the data.gov.in API key, failing loudly if not set."""
    settings = get_settings()
    key = settings.DATA_GOV_IN_API_KEY
    if not key or key == "your_api_key_here":
        raise ValueError(
            "DATA_GOV_IN_API_KEY is not set or is still the placeholder value. "
            "Register at https://data.gov.in to get an API key, then set it "
            "in your backend/.env file as DATA_GOV_IN_API_KEY=<your_key>"
        )
    return key


def _parse_date(date_str: str) -> Optional[date]:
    """Parse date string from API response. Handles multiple formats."""
    if not date_str:
        return None
    # data.gov.in returns dates in various formats
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d %b %Y"):
        try:
            return datetime.strptime(date_str.strip(), fmt).date()
        except ValueError:
            continue
    logger.warning(f"Could not parse date: {date_str}")
    return None


def _parse_price(price_val) -> Optional[float]:
    """Parse price value, returning None for invalid/missing data."""
    if price_val is None:
        return None
    try:
        val = float(str(price_val).strip())
        return val if val > 0 else None
    except (ValueError, TypeError):
        return None


def bulk_pull_historical(
    db: Session,
    commodity_slugs: list[str],
    start_date: date,
    end_date: date,
    page_size: int = 1000,
    use_historical_resource: bool = False,
) -> dict:
    """
    Bulk pull historical daily commodity prices from data.gov.in.

    Args:
        db: SQLAlchemy session
        commodity_slugs: List of commodity slugs (e.g., ["onion", "potato"])
        start_date: Start date for historical pull
        end_date: End date for historical pull
        page_size: Number of records per API page (max 1000)
        use_historical_resource: If True, uses the historical resource API with corresponding casing

    Returns:
        Dict with counts of records fetched and inserted per commodity
    """
    api_key = _get_api_key()
    results = {}

    resource_id = HISTORICAL_RESOURCE_ID if use_historical_resource else DAILY_RESOURCE_ID
    base_url = f"https://api.data.gov.in/resource/{resource_id}"

    for slug in commodity_slugs:
        api_commodity_name = COMMODITY_API_NAME_MAP.get(slug)
        if not api_commodity_name:
            logger.warning(f"No API mapping for commodity slug: {slug}")
            continue

        # Get or create commodity record
        commodity = db.execute(
            select(Commodity).where(Commodity.slug == slug)
        ).scalar_one_or_none()
        if not commodity:
            logger.warning(f"Commodity '{slug}' not found in DB. Skipping.")
            continue

        fetched = 0
        inserted = 0

        for mandi_name, mandi_api_info in MANDI_API_NAME_MAP.items():
            # Get mandi record
            mandi = db.execute(
                select(Mandi).where(Mandi.name == mandi_name)
            ).scalar_one_or_none()
            if not mandi:
                logger.warning(f"Mandi '{mandi_name}' not found in DB. Skipping.")
                continue

            logger.info(
                f"Pulling {api_commodity_name} from {mandi_name} "
                f"({start_date} to {end_date}) using "
                f"{'historical' if use_historical_resource else 'daily'} resource..."
            )

            offset = 0
            while True:
                # Build API request
                if use_historical_resource:
                    params = {
                        "api-key": api_key,
                        "format": "json",
                        "limit": page_size,
                        "offset": offset,
                        "filters[State]": "Tamil Nadu",
                        "filters[District]": mandi_api_info["district"],
                        "filters[Market]": mandi_api_info["market"],
                        "filters[Commodity]": api_commodity_name,
                    }
                else:
                    params = {
                        "api-key": api_key,
                        "format": "json",
                        "limit": page_size,
                        "offset": offset,
                        "filters[state.keyword]": "Tamil Nadu",
                        "filters[district]": mandi_api_info["district"],
                        "filters[market]": mandi_api_info["market"],
                        "filters[commodity]": api_commodity_name,
                    }

                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json",
                }

                try:
                    # data.gov.in can be very slow; use generous timeout
                    # and retry up to 3 times with backoff
                    response = None
                    for attempt in range(3):
                        try:
                            response = httpx.get(
                                base_url, params=params, headers=headers, timeout=60.0
                            )
                            response.raise_for_status()
                            break
                        except (httpx.TimeoutException, httpx.ConnectError) as retry_err:
                            if attempt < 2:
                                wait_secs = (attempt + 1) * 10
                                logger.warning(
                                    f"  Attempt {attempt+1} failed: {retry_err}. "
                                    f"Retrying in {wait_secs}s..."
                                )
                                import time
                                time.sleep(wait_secs)
                            else:
                                raise
                    data = response.json()
                except httpx.HTTPError as e:
                    logger.error(
                        f"API request failed for {api_commodity_name} at "
                        f"{mandi_name}: {e}"
                    )
                    break
                except Exception as e:
                    logger.error(f"Unexpected error: {e}")
                    break

                records = data.get("records", [])
                if not records:
                    break

                page_fetched = len(records)
                fetched += page_fetched

                for record in records:
                    obs_date = _parse_date(
                        record.get("Arrival_Date", "")
                    )
                    if obs_date is None:
                        continue

                    # Filter by date range
                    if obs_date < start_date or obs_date > end_date:
                        continue

                    min_price = _parse_price(
                        record.get("Min_x0020_Price")
                        or record.get("Min Price")
                        or record.get("min_price")
                        or record.get("Min_Price")
                    )
                    max_price = _parse_price(
                        record.get("Max_x0020_Price")
                        or record.get("Max Price")
                        or record.get("max_price")
                        or record.get("Max_Price")
                    )
                    modal_price = _parse_price(
                        record.get("Modal_x0020_Price")
                        or record.get("Modal Price")
                        or record.get("modal_price")
                        or record.get("Modal_Price")
                    )

                    if modal_price is None and min_price is None:
                        continue  # Skip rows with no usable price data

                    # Upsert using MySQL INSERT ... ON DUPLICATE KEY UPDATE
                    stmt = mysql_insert(PriceObservation).values(
                        commodity_id=commodity.id,
                        mandi_id=mandi.id,
                        date=obs_date,
                        min_price=min_price,
                        max_price=max_price,
                        modal_price=modal_price,
                        arrival_qty=None,  # Not consistently available
                    )
                    stmt = stmt.on_duplicate_key_update(
                        min_price=stmt.inserted.min_price,
                        max_price=stmt.inserted.max_price,
                        modal_price=stmt.inserted.modal_price,
                    )
                    db.execute(stmt)
                    inserted += 1

                db.commit()

                # Check if we've gotten all records
                total = data.get("total", 0)
                if isinstance(total, str):
                    total = int(total)
                offset += page_size
                if offset >= total or page_fetched < page_size:
                    break

                logger.info(
                    f"  Page complete. Offset: {offset}/{total}. "
                    f"Fetched: {fetched}"
                )

        results[slug] = {"fetched": fetched, "inserted": inserted}
        logger.info(
            f"[{slug}] Total fetched: {fetched}, inserted/updated: {inserted}"
        )

    return results


def daily_pull(db: Session, target_date: Optional[date] = None) -> dict:
    """
    Pull a single day's commodity prices (default: yesterday).

    Idempotent — running twice for the same date will update existing
    rows rather than creating duplicates (enforced by DB unique constraint
    + ON DUPLICATE KEY UPDATE).

    Args:
        db: SQLAlchemy session
        target_date: Date to pull data for (default: yesterday)

    Returns:
        Dict with counts per commodity
    """
    if target_date is None:
        target_date = date.today() - timedelta(days=1)

    logger.info(f"Daily pull for date: {target_date}")

    all_slugs = list(COMMODITY_API_NAME_MAP.keys())
    return bulk_pull_historical(
        db=db,
        commodity_slugs=all_slugs,
        start_date=target_date,
        end_date=target_date,
    )
