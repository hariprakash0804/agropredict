"""
AgroPredict - Historical Data Backfill Script

Pulls historical commodity prices from data.gov.in and weather data
from Open-Meteo for the configured mandis and commodities.

Usage:
    python scripts/backfill.py --commodities onion,potato,tomato,tur_dal --years 3
"""

import argparse
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Add backend directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, select
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.core.database import Base
from app.ingestion.agmarknet import bulk_pull_historical
from app.ingestion.mandi_geocoding import (
    COMMODITY_SEED_DATA,
    MANDI_SEED_DATA,
)
from app.ingestion.openmeteo import pull_weather_all_mandis
from app.models.commodity import Commodity, Mandi, PriceObservation, WeatherObservation

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("backfill")


def seed_commodities_and_mandis(db_session):
    """Seed the Commodity and Mandi tables if they don't exist."""
    logger.info("Seeding commodities...")
    for c_data in COMMODITY_SEED_DATA:
        existing = db_session.execute(
            select(Commodity).where(Commodity.slug == c_data["slug"])
        ).scalar_one_or_none()
        if not existing:
            commodity = Commodity(name=c_data["name"], slug=c_data["slug"])
            db_session.add(commodity)
            logger.info(f"  Created commodity: {c_data['name']}")
        else:
            logger.info(f"  Commodity already exists: {c_data['name']}")
    db_session.commit()

    logger.info("Seeding mandis...")
    for m_data in MANDI_SEED_DATA:
        existing = db_session.execute(
            select(Mandi).where(
                Mandi.name == m_data["name"],
                Mandi.district == m_data["district"],
            )
        ).scalar_one_or_none()
        if not existing:
            mandi = Mandi(**m_data)
            db_session.add(mandi)
            logger.info(f"  Created mandi: {m_data['name']} ({m_data['district']})")
        else:
            logger.info(
                f"  Mandi already exists: {m_data['name']} ({m_data['district']})"
            )
    db_session.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Backfill historical commodity and weather data"
    )
    parser.add_argument(
        "--commodities",
        type=str,
        default="onion,potato,tomato,tur_dal",
        help="Comma-separated list of commodity slugs",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Number of years of history to pull",
    )
    parser.add_argument(
        "--skip-weather",
        action="store_true",
        help="Skip weather data pull (useful for faster testing)",
    )
    args = parser.parse_args()

    commodity_slugs = [s.strip() for s in args.commodities.split(",")]
    end_date = date.today() - timedelta(days=1)
    start_date = date(end_date.year - args.years, end_date.month, end_date.day)

    logger.info("=" * 60)
    logger.info("AgroPredict Historical Backfill")
    logger.info(f"  Commodities: {commodity_slugs}")
    logger.info(f"  Date range: {start_date} to {end_date}")
    logger.info(f"  Years: {args.years}")
    logger.info("=" * 60)

    # Create sync engine (scripts use synchronous DB access)
    settings = get_settings()
    sync_url = settings.SYNC_DATABASE_URL
    engine = create_engine(sync_url, echo=False)

    # Create tables if they don't exist
    logger.info("Creating database tables...")
    Base.metadata.create_all(engine)
    logger.info("Database tables ready.")

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Step 1: Seed commodities and mandis
        seed_commodities_and_mandis(db)

        # Step 2: Pull commodity prices from data.gov.in
        logger.info("")
        logger.info("=" * 60)
        logger.info("STEP 1: Pulling commodity prices from data.gov.in...")
        logger.info("=" * 60)
        price_results = bulk_pull_historical(
            db=db,
            commodity_slugs=commodity_slugs,
            start_date=start_date,
            end_date=end_date,
        )
        for slug, counts in price_results.items():
            logger.info(
                f"  {slug}: fetched={counts['fetched']}, "
                f"inserted/updated={counts['inserted']}"
            )

        # Step 3: Pull weather data from Open-Meteo
        if not args.skip_weather:
            logger.info("")
            logger.info("=" * 60)
            logger.info("STEP 2: Pulling weather data from Open-Meteo...")
            logger.info("=" * 60)
            weather_results = pull_weather_all_mandis(
                db=db,
                start_date=start_date,
                end_date=end_date,
            )
            for mandi_name, count in weather_results.items():
                logger.info(f"  {mandi_name}: {count} records")
        else:
            logger.info("Skipping weather data pull (--skip-weather flag).")

        # Summary
        logger.info("")
        logger.info("=" * 60)
        logger.info("BACKFILL COMPLETE")
        price_count = db.execute(
            select(PriceObservation).with_only_columns(
                __import__("sqlalchemy").func.count()
            )
        ).scalar()
        weather_count = db.execute(
            select(WeatherObservation).with_only_columns(
                __import__("sqlalchemy").func.count()
            )
        ).scalar()
        logger.info(f"  Total price observations: {price_count}")
        logger.info(f"  Total weather observations: {weather_count}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Backfill failed: {e}", exc_info=True)
        raise
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
