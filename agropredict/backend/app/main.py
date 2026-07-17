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

# Configure CORS origins dynamically
cors_origins = ["http://localhost:3000"]
if settings.FRONTEND_URL:
    clean_origin = settings.FRONTEND_URL.strip().rstrip("/")
    cors_origins.extend([clean_origin, f"{clean_origin}/"])

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
from app.api.endpoints import router as api_router
app.include_router(api_router, prefix="/api")


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



