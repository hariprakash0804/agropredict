"""
AgroPredict - Daily Incremental Data Pull Script

Pulls yesterday's commodity prices and weather data for all configured
commodities and mandis. Designed to be triggered daily by APScheduler
or external cron.

Usage:
    python scripts/daily_pull.py
    python scripts/daily_pull.py --date 2024-01-15
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

# Add backend directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.ingestion.agmarknet import daily_pull as agmarknet_daily
from app.ingestion.openmeteo import daily_weather_pull

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("daily_pull")


def main():
    parser = argparse.ArgumentParser(
        description="Daily incremental commodity + weather data pull"
    )
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD format (default: yesterday)",
    )
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = date.today() - timedelta(days=1)

    logger.info(f"Daily pull for date: {target_date}")

    # Create sync engine
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Pull commodity prices
        logger.info("Pulling commodity prices...")
        price_results = agmarknet_daily(db, target_date)
        for slug, counts in price_results.items():
            logger.info(
                f"  {slug}: fetched={counts['fetched']}, "
                f"inserted/updated={counts['inserted']}"
            )

        # Pull weather data
        logger.info("Pulling weather data...")
        weather_results = daily_weather_pull(db, target_date)
        for mandi_name, count in weather_results.items():
            logger.info(f"  {mandi_name}: {count} weather records")

        logger.info("Daily pull complete.")

    except Exception as e:
        logger.error(f"Daily pull failed: {e}", exc_info=True)
        raise
    finally:
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
