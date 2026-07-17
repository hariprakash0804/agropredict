"""
AgroPredict - Weather-Only Backfill Script

Test script to verify Open-Meteo weather ingestion works independently
of the data.gov.in API key.

Usage:
    python scripts/backfill_weather.py --years 3
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, func, select
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.ingestion.openmeteo import pull_weather_all_mandis
from app.models.commodity import WeatherObservation

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("weather_backfill")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Backfill weather data only")
    parser.add_argument("--years", type=int, default=3)
    args = parser.parse_args()

    end_date = date.today() - timedelta(days=2)
    start_date = date(end_date.year - args.years, end_date.month, end_date.day)

    logger.info(f"Weather backfill: {start_date} to {end_date}")

    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        results = pull_weather_all_mandis(db, start_date, end_date)
        for mandi_name, count in results.items():
            logger.info(f"  {mandi_name}: {count} records")

        total = db.execute(
            select(func.count()).select_from(WeatherObservation)
        ).scalar()
        logger.info(f"Total weather observations: {total}")
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
