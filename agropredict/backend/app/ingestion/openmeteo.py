"""
AgroPredict - Open-Meteo Weather Data Ingestion

Pulls historical daily weather data from the Open-Meteo Archive API.
Endpoint: https://archive-api.open-meteo.com/v1/archive
No API key required.

Variables fetched:
- temperature_2m_max: Maximum daily air temperature (Celsius)
- temperature_2m_min: Minimum daily air temperature (Celsius)
- precipitation_sum: Total daily precipitation (mm)
"""

import logging
from datetime import date, timedelta
from typing import Optional

import httpx
# pyrefly: ignore [missing-import]
from sqlalchemy import select
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.mysql import insert as mysql_insert
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import Session

from app.models.commodity import Mandi, WeatherObservation

logger = logging.getLogger(__name__)

ARCHIVE_API_URL = "https://archive-api.open-meteo.com/v1/archive"

# Open-Meteo limits: max ~10000 days per request, but we chunk by year
# for reliability
MAX_DAYS_PER_REQUEST = 365


def pull_weather_for_mandi(
    db: Session,
    mandi: Mandi,
    start_date: date,
    end_date: date,
) -> int:
    """
    Pull historical weather data for a single mandi location.

    Args:
        db: SQLAlchemy session
        mandi: Mandi model instance (has latitude, longitude)
        start_date: Start date for weather data
        end_date: End date for weather data

    Returns:
        Number of records inserted/updated
    """
    inserted = 0
    current_start = start_date

    while current_start <= end_date:
        # Chunk by year to avoid overwhelming the API
        current_end = min(
            current_start + timedelta(days=MAX_DAYS_PER_REQUEST - 1),
            end_date,
        )

        # Ensure we don't request future dates (Open-Meteo archive
        # only has data up to ~5 days ago)
        today = date.today()
        if current_end >= today:
            current_end = today - timedelta(days=2)
        if current_start >= today:
            break

        logger.info(
            f"  Fetching weather for {mandi.name} "
            f"({current_start} to {current_end})..."
        )

        params = {
            "latitude": mandi.latitude,
            "longitude": mandi.longitude,
            "start_date": current_start.isoformat(),
            "end_date": current_end.isoformat(),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "timezone": "Asia/Kolkata",
        }

        try:
            response = httpx.get(
                ARCHIVE_API_URL, params=params, timeout=30.0
            )
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(
                f"Open-Meteo API request failed for {mandi.name}: {e}"
            )
            current_start = current_end + timedelta(days=1)
            continue
        except Exception as e:
            logger.error(f"Unexpected error fetching weather: {e}")
            current_start = current_end + timedelta(days=1)
            continue

        daily = data.get("daily", {})
        dates = daily.get("time", [])
        temp_maxes = daily.get("temperature_2m_max", [])
        temp_mins = daily.get("temperature_2m_min", [])
        precip_sums = daily.get("precipitation_sum", [])

        if not dates:
            logger.warning(
                f"No weather data returned for {mandi.name} "
                f"({current_start} to {current_end})"
            )
            current_start = current_end + timedelta(days=1)
            continue

        for i, date_str in enumerate(dates):
            obs_date = date.fromisoformat(date_str)

            temp_max = temp_maxes[i] if i < len(temp_maxes) else None
            temp_min = temp_mins[i] if i < len(temp_mins) else None
            precip = precip_sums[i] if i < len(precip_sums) else None

            # Upsert using MySQL INSERT ... ON DUPLICATE KEY UPDATE
            stmt = mysql_insert(WeatherObservation).values(
                mandi_id=mandi.id,
                date=obs_date,
                temp_max=temp_max,
                temp_min=temp_min,
                precipitation_mm=precip,
            )
            stmt = stmt.on_duplicate_key_update(
                temp_max=stmt.inserted.temp_max,
                temp_min=stmt.inserted.temp_min,
                precipitation_mm=stmt.inserted.precipitation_mm,
            )
            db.execute(stmt)
            inserted += 1

        db.commit()

        logger.info(
            f"  Inserted/updated {len(dates)} weather records for "
            f"{mandi.name}"
        )
        current_start = current_end + timedelta(days=1)

    return inserted


def pull_weather_all_mandis(
    db: Session,
    start_date: date,
    end_date: date,
) -> dict:
    """
    Pull historical weather data for all mandis in the database.

    Args:
        db: SQLAlchemy session
        start_date: Start date
        end_date: End date

    Returns:
        Dict mapping mandi name to number of records inserted
    """
    mandis = db.execute(select(Mandi)).scalars().all()
    results = {}

    for mandi in mandis:
        logger.info(f"Pulling weather for mandi: {mandi.name}")
        count = pull_weather_for_mandi(db, mandi, start_date, end_date)
        results[mandi.name] = count

    return results


def daily_weather_pull(
    db: Session,
    target_date: Optional[date] = None,
) -> dict:
    """
    Pull yesterday's weather data for all mandis.

    Args:
        db: SQLAlchemy session
        target_date: Date to pull (default: day before yesterday for
                     data availability)

    Returns:
        Dict mapping mandi name to records inserted
    """
    if target_date is None:
        # Open-Meteo archive has ~2 day lag
        target_date = date.today() - timedelta(days=2)

    return pull_weather_all_mandis(db, target_date, target_date)
