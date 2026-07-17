"""
AgroPredict - Background Scheduler Service (APScheduler)

Replaces n8n orchestration. Periodically triggers daily incremental pulls
of commodity prices and weather observations to keep the database fresh.
"""
import logging
from datetime import date, timedelta
# pyrefly: ignore [missing-import]
from apscheduler.schedulers.background import BackgroundScheduler
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings
from app.ingestion.agmarknet import daily_pull as agmarknet_daily
from app.ingestion.openmeteo import daily_weather_pull

logger = logging.getLogger(__name__)

# Initialize background scheduler
scheduler = BackgroundScheduler(daemon=True)

def daily_data_ingestion_job():
    """Daily cron job to pull yesterday's prices and weather."""
    logger.info("Executing scheduled daily data ingestion job...")
    
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        # Pull yesterday's commodity prices
        target_date = date.today() - timedelta(days=1)
        logger.info(f"Ingesting daily commodity prices for {target_date}...")
        price_results = agmarknet_daily(db, target_date)
        for slug, counts in price_results.items():
            logger.info(f"  {slug}: fetched={counts['fetched']}, inserted={counts['inserted']}")
            
        # Pull weather observations (2 days lag for Open-Meteo archive)
        weather_date = date.today() - timedelta(days=2)
        logger.info(f"Ingesting daily weather observations for {weather_date}...")
        weather_results = daily_weather_pull(db, weather_date)
        for mandi_name, count in weather_results.items():
            logger.info(f"  {mandi_name}: inserted={count} weather records")
            
        logger.info("Scheduled daily data ingestion job completed successfully.")
        
    except Exception as e:
        logger.error(f"Error in scheduled daily ingestion job: {e}", exc_info=True)
    finally:
        db.close()
        engine.dispose()

def start_scheduler():
    """Starts the background scheduler and adds cron jobs."""
    # Run daily at 06:00 AM IST (which is 00:30 AM UTC)
    # We also add a trigger to run 10 seconds after startup for validation
    scheduler.add_job(
        daily_data_ingestion_job,
        trigger="cron",
        hour=6,
        minute=0,
        id="daily_data_pull",
        replace_existing=True
    )
    
    # Optional: trigger immediately on startup (for test verification in logs)
    # scheduler.add_job(daily_data_ingestion_job, id="startup_test_run")
    
    scheduler.start()
    logger.info("APScheduler service started successfully.")

def shutdown_scheduler():
    """Shuts down the background scheduler."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("APScheduler service shut down successfully.")
