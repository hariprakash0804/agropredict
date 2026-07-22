"""
AgroPredict - Agricultural Commodity Price Forecasting System

FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.database import check_db_connection
from app.core.redis_client import check_redis_connection


settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup and shutdown events."""
    # Startup
    print("[AgroPredict] Ensuring database tables exist...")
    from app.core.database import engine
    from app.models.commodity import Base, User, UserQueryLog, Commodity, Mandi, PriceObservation, WeatherObservation, ForecastAccuracy
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Lightweight migrations
        from sqlalchemy import text
        for col in ["variety", "grade"]:
            try:
                await conn.execute(text(f"ALTER TABLE price_observations ADD COLUMN {col} VARCHAR(100) DEFAULT 'FAQ'"))
                print(f"[AgroPredict] Migration: Added column '{col}' to price_observations.")
            except Exception:
                # Column already exists, ignore
                pass

        # Robust column migration for users.email
        try:
            res = await conn.execute(text("SHOW COLUMNS FROM users LIKE 'email'"))
            if not res.scalar_one_or_none():
                print("[AgroPredict] Migration: Adding 'email' column to users table...")
                await conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(100) NULL"))
                try:
                    await conn.execute(text("UPDATE users SET email = username WHERE email IS NULL AND username IS NOT NULL"))
                    await conn.execute(text("CREATE UNIQUE INDEX ix_users_email ON users (email)"))
                except Exception as idx_err:
                    print(f"[AgroPredict] Index/Update note: {idx_err}")
                print("[AgroPredict] Migration SUCCESS: 'email' column added to users table.")
            else:
                print("[AgroPredict] Migration: 'email' column already present in users table.")
        except Exception as e:
            print(f"[AgroPredict] Migration error checking users.email: {e}")
            # Direct fallback alter attempt
            try:
                await conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(100)"))
                print("[AgroPredict] Migration Fallback: Added 'email' column.")
            except Exception:
                pass
    print("[AgroPredict] Database tables verified.")

    print("[AgroPredict] Starting background scheduler...")
    from app.services.scheduler import start_scheduler, shutdown_scheduler
    start_scheduler()
    print("[AgroPredict] Background scheduler started.")
    
    print("[AgroPredict] Backend starting up...")
    yield
    # Shutdown
    print("[AgroPredict] Stopping background scheduler...")
    shutdown_scheduler()
    print("[AgroPredict] Background scheduler stopped.")
    print("[AgroPredict] Backend shutting down...")


app = FastAPI(
    title="AgroPredict API",
    description=(
        "Production-grade agricultural commodity price forecasting "
        "system for the Indian market. Provides historical price data, "
        "weather-informed forecasts using Chronos-2, and live accuracy monitoring."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for cross-origin requests (Vercel frontend calling Render backend)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
from app.api.endpoints import router as api_router
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint for status verification."""
    return {"status": "ok", "message": "AgroPredict API is running"}


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint.

    Performs a real connection check against MySQL and Redis,
    returning their actual connectivity status — not hardcoded values.
    """
    db_ok = await check_db_connection()
    redis_ok = await check_redis_connection()

    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "db": db_ok,
        "redis": redis_ok,
    }



