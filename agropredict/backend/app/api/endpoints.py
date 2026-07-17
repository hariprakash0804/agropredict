"""
AgroPredict - API Endpoints
"""
import json
from datetime import date, timedelta, datetime
from typing import List, Optional
from pydantic import BaseModel
import httpx
import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.config import get_settings

from app.core.database import get_db
from app.core.redis_client import get_redis
from app.models.commodity import Commodity, Mandi, PriceObservation, WeatherObservation, ForecastLog, ForecastAccuracy, User, UserQueryLog
from app.schemas.commodity import (
    CommodityOut,
    ForecastResponse,
    HistoryResponse,
    MandiOut,
    PriceObservationOut,
    WeatherObservationOut,
    ForecastAccuracyOut,
)

router = APIRouter()

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"


async def fetch_future_weather(latitude: float, longitude: float, horizon: int) -> List[dict]:
    """
    Fetch future weather forecast from Open-Meteo API.
    For dates past 16 days, falls back to climatology/averages of the forecast.
    """
    forecast_days = min(horizon, 16)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
        "timezone": "Asia/Kolkata",
        "forecast_days": forecast_days,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(OPEN_METEO_FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
            
            daily = data.get("daily", {})
            times = daily.get("time", [])
            t_maxes = daily.get("temperature_2m_max", [])
            t_mins = daily.get("temperature_2m_min", [])
            precips = daily.get("precipitation_sum", [])
            
            weather_list = []
            for i in range(len(times)):
                weather_list.append({
                    "date": date.fromisoformat(times[i]),
                    "temp_max": t_maxes[i] if t_maxes[i] is not None else 30.0,
                    "temp_min": t_mins[i] if t_mins[i] is not None else 22.0,
                    "precipitation_mm": precips[i] if precips[i] is not None else 0.0,
                })
                
            # If we need more days (up to 30 days), pad with the average of the fetched forecast
            if len(weather_list) < horizon:
                avg_max = np.mean([w["temp_max"] for w in weather_list]) if weather_list else 30.0
                avg_min = np.mean([w["temp_min"] for w in weather_list]) if weather_list else 22.0
                avg_precip = np.mean([w["precipitation_mm"] for w in weather_list]) if weather_list else 0.0
                
                last_date = weather_list[-1]["date"] if weather_list else date.today()
                for day in range(1, horizon - len(weather_list) + 1):
                    weather_list.append({
                        "date": last_date + timedelta(days=day),
                        "temp_max": float(avg_max),
                        "temp_min": float(avg_min),
                        "precipitation_mm": float(avg_precip),
                    })
                    
            return weather_list
            
    except Exception as e:
        print(f"Error fetching Open-Meteo forecast: {e}")
        # Return fallback weather data
        fallback_list = []
        today = date.today()
        for day in range(1, horizon + 1):
            fallback_list.append({
                "date": today + timedelta(days=day),
                "temp_max": 32.0,
                "temp_min": 24.0,
                "precipitation_mm": 0.0,
            })
        return fallback_list


async def geocode_mandi(mandi_name: str) -> tuple[float, float]:
    """Geocode any mandi location using Open-Meteo Geocoding API."""
    url = f"https://geocoding-api.open-meteo.com/v1/search?name={mandi_name}&count=1&language=en&format=json"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, timeout=10.0)
            if resp.status_code == 200:
                results = resp.json().get("results", [])
                if results:
                    return float(results[0]["latitude"]), float(results[0]["longitude"])
    except Exception as e:
        print(f"Error geocoding mandi {mandi_name}: {e}")
    # Default fallback to Salem coordinates
    return 11.6643, 78.1460


async def backfill_weather_for_mandi(db: AsyncSession, mandi_id: int, lat: float, lon: float, start_date: date, end_date: date):
    """Backfill weather observations for a new mandi dynamically."""
    archive_url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": ["temperature_2m_max", "temperature_2m_min", "precipitation_sum"],
        "timezone": "auto",
    }
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(archive_url, params=params, timeout=20.0)
            if resp.status_code == 200:
                daily = resp.json().get("daily", {})
                times = daily.get("time", [])
                t_maxes = daily.get("temperature_2m_max", [])
                t_mins = daily.get("temperature_2m_min", [])
                precips = daily.get("precipitation_sum", [])
                
                for i in range(len(times)):
                    obs_date = date.fromisoformat(times[i])
                    stmt = mysql_insert(WeatherObservation).values(
                        mandi_id=mandi_id,
                        date=obs_date,
                        temp_max=t_maxes[i],
                        temp_min=t_mins[i],
                        precipitation_mm=precips[i]
                    )
                    stmt = stmt.on_duplicate_key_update(
                        temp_max=stmt.inserted.temp_max,
                        temp_min=stmt.inserted.temp_min,
                        precipitation_mm=stmt.inserted.precipitation_mm
                    )
                    await db.execute(stmt)
                await db.commit()
    except Exception as e:
        print(f"Error backfilling weather: {e}")


async def fetch_prices_from_api(
    state: str,
    district: str,
    mandi_name: str,
    commodity_name: str,
    start_date: date,
    end_date: date,
) -> List[dict]:
    """
    Fetch prices from data.gov.in dynamically for any state/district/mandi/commodity.
    """
    api_key = get_settings().DATA_GOV_IN_API_KEY
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
    }
    
    # Try historical resource first (casing: State, District, Commodity)
    hist_url = "https://api.data.gov.in/resource/35985678-0d79-46b4-9ed6-6f13308a1d24"
    params = {
        "api-key": api_key,
        "format": "json",
        "limit": 1000,
        "filters[State]": state,
        "filters[District]": district,
        "filters[Commodity]": commodity_name,
    }
    
    records = []
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(hist_url, params=params, headers=headers, timeout=20.0)
            if resp.status_code == 200:
                records = resp.json().get("records", [])
    except Exception as e:
        print(f"Error fetching from historical API: {e}")
        
    # If no records, try daily resource (casing: state.keyword, district, commodity)
    if not records:
        daily_url = "https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070"
        params_daily = {
            "api-key": api_key,
            "format": "json",
            "limit": 1000,
            "filters[state.keyword]": state,
            "filters[district]": district,
            "filters[commodity]": commodity_name,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(daily_url, params=params_daily, headers=headers, timeout=20.0)
                if resp.status_code == 200:
                    records = resp.json().get("records", [])
        except Exception as e:
            print(f"Error fetching from daily API: {e}")
            
    # Parse records
    parsed_records = []
    for r in records:
        market_field = r.get("Market") or r.get("market") or ""
        # Handle fuzzy match/substring check
        if mandi_name.lower() not in market_field.lower():
            continue
            
        date_str = r.get("Arrival_Date") or r.get("arrival_date") or ""
        obs_date = None
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                obs_date = datetime.strptime(date_str.strip(), fmt).date()
                break
            except ValueError:
                continue
                
        if not obs_date:
            continue
            
        if obs_date < start_date or obs_date > end_date:
            continue
            
        min_price = r.get("Min_Price") or r.get("Min Price") or r.get("min_price") or r.get("Min_x0020_Price")
        max_price = r.get("Max_Price") or r.get("Max Price") or r.get("max_price") or r.get("Max_x0020_Price")
        modal_price = r.get("Modal_Price") or r.get("Modal Price") or r.get("modal_price") or r.get("Modal_x0020_Price")
        
        try:
            parsed_records.append({
                "date": obs_date,
                "min_price": float(min_price) if min_price else None,
                "max_price": float(max_price) if max_price else None,
                "modal_price": float(modal_price) if modal_price else None,
            })
        except Exception:
            continue
            
    return parsed_records


@router.get("/commodities", response_model=List[CommodityOut], tags=["Commodities"])
async def get_commodities(db: AsyncSession = Depends(get_db)):
    """Get all supported commodities."""
    result = await db.execute(select(Commodity))
    return result.scalars().all()


@router.get("/mandis", response_model=List[MandiOut], tags=["Mandis"])
async def get_mandis(db: AsyncSession = Depends(get_db)):
    """Get all supported mandis."""
    result = await db.execute(select(Mandi))
    return result.scalars().all()


@router.get("/history/{commodity_slug}/{mandi_name}", response_model=HistoryResponse, tags=["Forecasting"])
async def get_history(
    commodity_slug: str,
    mandi_name: str,
    state: str = "Tamil Nadu",
    district: str = "Salem",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Fetch historical price and weather observations for a commodity-mandi pair (pulling live if not cached)."""
    # 1. Parse dates
    today = date.today()
    s_date = date.fromisoformat(start_date) if start_date else today - timedelta(days=180)
    e_date = date.fromisoformat(end_date) if end_date else today
    
    # 2. Get or create Commodity
    comm_res = await db.execute(select(Commodity).where(Commodity.slug == commodity_slug))
    commodity = comm_res.scalar_one_or_none()
    if not commodity:
        try:
            commodity_name = commodity_slug.replace('-', ' ').title()
            commodity = Commodity(name=commodity_name, slug=commodity_slug)
            db.add(commodity)
            await db.commit()
            await db.refresh(commodity)
        except Exception:
            await db.rollback()
            comm_res = await db.execute(select(Commodity).where(Commodity.slug == commodity_slug))
            commodity = comm_res.scalar_one()
        
    # 3. Get or create Mandi
    mandi_res = await db.execute(select(Mandi).where(Mandi.name == mandi_name))
    mandi = mandi_res.scalar_one_or_none()
    if not mandi:
        try:
            # Geocode dynamically
            lat, lon = await geocode_mandi(mandi_name)
            mandi = Mandi(name=mandi_name, state=state, district=district, latitude=lat, longitude=lon)
            db.add(mandi)
            await db.commit()
            await db.refresh(mandi)
            # Backfill weather observations for the new mandi dynamically
            await backfill_weather_for_mandi(db, mandi.id, lat, lon, today - timedelta(days=365), today)
        except Exception:
            await db.rollback()
            mandi_res = await db.execute(select(Mandi).where(Mandi.name == mandi_name))
            mandi = mandi_res.scalar_one()

    # 4. Fetch prices from DB
    prices_res = await db.execute(
        select(PriceObservation)
        .where(PriceObservation.commodity_id == commodity.id, PriceObservation.mandi_id == mandi.id)
        .where(PriceObservation.date >= s_date, PriceObservation.date <= e_date)
        .order_by(PriceObservation.date.desc())
    )
    prices = prices_res.scalars().all()
    
    # If no prices found locally, pull dynamically from API
    if len(prices) < 5:
        print(f"Dynamically fetching prices from data.gov.in for {commodity.name} at {mandi.name}...")
        api_records = await fetch_prices_from_api(state, district, mandi_name, commodity.name, s_date, e_date)
        if api_records:
            for r in api_records:
                stmt = mysql_insert(PriceObservation).values(
                    commodity_id=commodity.id,
                    mandi_id=mandi.id,
                    date=r["date"],
                    min_price=r["min_price"],
                    max_price=r["max_price"],
                    modal_price=r["modal_price"]
                )
                stmt = stmt.on_duplicate_key_update(
                    min_price=stmt.inserted.min_price,
                    max_price=stmt.inserted.max_price,
                    modal_price=stmt.inserted.modal_price
                )
                await db.execute(stmt)
            await db.commit()
            
            # Re-query prices
            prices_res = await db.execute(
                select(PriceObservation)
                .where(PriceObservation.commodity_id == commodity.id, PriceObservation.mandi_id == mandi.id)
                .where(PriceObservation.date >= s_date, PriceObservation.date <= e_date)
                .order_by(PriceObservation.date.desc())
            )
            prices = prices_res.scalars().all()

    # Reverse to chronological order
    prices.reverse()
    
    # Fetch weather
    weather_res = await db.execute(
        select(WeatherObservation)
        .where(WeatherObservation.mandi_id == mandi.id)
        .where(WeatherObservation.date >= s_date, WeatherObservation.date <= e_date)
        .order_by(WeatherObservation.date.desc())
    )
    weather = weather_res.scalars().all()
    weather.reverse()
    
    return HistoryResponse(
        commodity=commodity.name,
        mandi=mandi.name,
        prices=[PriceObservationOut.model_validate(p) for p in prices],
        weather=[WeatherObservationOut.model_validate(w) for w in weather]
    )


async def log_forecast_to_db(
    commodity_id: int,
    mandi_id: int,
    forecast_dates: List[date],
    p10: List[float],
    p50: List[float],
    p90: List[float],
    model_name: str
):
    """
    Background task to log served forecasts for accuracy evaluation.
    Opens a separate async session since the request session might be closed.
    """
    from app.core.database import async_session_factory
    from datetime import datetime
    
    async with async_session_factory() as session:
        try:
            now = datetime.now()
            for i, f_date in enumerate(forecast_dates):
                log_entry = ForecastLog(
                    commodity_id=commodity_id,
                    mandi_id=mandi_id,
                    forecast_date=f_date,
                    created_at=now,
                    p10=p10[i],
                    p50=p50[i],
                    p90=p90[i],
                    model_name=model_name
                )
                session.add(log_entry)
            await session.commit()
        except Exception as e:
            print(f"Error logging forecast to DB: {e}")


@router.get("/forecast/{commodity_slug}/{mandi_name}", response_model=ForecastResponse, tags=["Forecasting"])
async def get_forecast(
    request: Request,
    commodity_slug: str,
    mandi_name: str,
    background_tasks: BackgroundTasks,
    state: str = "Tamil Nadu",
    district: str = "Salem",
    horizon: int = 30,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis)
):
    """
    Get price forecasts for the next N days.
    Caches results in Redis with a 24-hour TTL.
    """
    if horizon not in [7, 30]:
        raise HTTPException(status_code=400, detail="Horizon must be either 7 or 30 days")
        
    # 1. Check Redis Cache
    cache_key = f"forecast:{commodity_slug}:{mandi_name}:{horizon}"
    try:
        cached_data = await redis.get(cache_key)
        if cached_data:
            return ForecastResponse(**json.loads(cached_data))
    except Exception as e:
        print(f"Redis cache read error: {e}")
        
    # 2. Get or create Commodity
    comm_res = await db.execute(select(Commodity).where(Commodity.slug == commodity_slug))
    commodity = comm_res.scalar_one_or_none()
    if not commodity:
        try:
            commodity_name = commodity_slug.replace('-', ' ').title()
            commodity = Commodity(name=commodity_name, slug=commodity_slug)
            db.add(commodity)
            await db.commit()
            await db.refresh(commodity)
        except Exception:
            await db.rollback()
            comm_res = await db.execute(select(Commodity).where(Commodity.slug == commodity_slug))
            commodity = comm_res.scalar_one()
        
    # 3. Get or create Mandi
    mandi_res = await db.execute(select(Mandi).where(Mandi.name == mandi_name))
    mandi = mandi_res.scalar_one_or_none()
    if not mandi:
        try:
            # Geocode dynamically
            lat, lon = await geocode_mandi(mandi_name)
            mandi = Mandi(name=mandi_name, state=state, district=district, latitude=lat, longitude=lon)
            db.add(mandi)
            await db.commit()
            await db.refresh(mandi)
            # Backfill weather observations for the new mandi dynamically
            await backfill_weather_for_mandi(db, mandi.id, lat, lon, date.today() - timedelta(days=365), date.today())
        except Exception:
            await db.rollback()
            mandi_res = await db.execute(select(Mandi).where(Mandi.name == mandi_name))
            mandi = mandi_res.scalar_one()
        
    # 4. Fetch historical data (last 120 days to construct features/context)
    prices_res = await db.execute(
        select(PriceObservation.date, PriceObservation.modal_price)
        .where(PriceObservation.commodity_id == commodity.id, PriceObservation.mandi_id == mandi.id)
        .order_by(PriceObservation.date.desc())
        .limit(120)
    )
    prices = prices_res.all()
    
    # If no prices found locally, pull dynamically from API
    if len(prices) < 5:
        print(f"Dynamically fetching prices for forecasting from data.gov.in...")
        today = date.today()
        api_records = await fetch_prices_from_api(state, district, mandi_name, commodity.name, today - timedelta(days=120), today)
        if api_records:
            for r in api_records:
                stmt = mysql_insert(PriceObservation).values(
                    commodity_id=commodity.id,
                    mandi_id=mandi.id,
                    date=r["date"],
                    min_price=r["min_price"],
                    max_price=r["max_price"],
                    modal_price=r["modal_price"]
                )
                stmt = stmt.on_duplicate_key_update(
                    min_price=stmt.inserted.min_price,
                    max_price=stmt.inserted.max_price,
                    modal_price=stmt.inserted.modal_price
                )
                await db.execute(stmt)
            await db.commit()
            
            # Re-fetch
            prices_res = await db.execute(
                select(PriceObservation.date, PriceObservation.modal_price)
                .where(PriceObservation.commodity_id == commodity.id, PriceObservation.mandi_id == mandi.id)
                .order_by(PriceObservation.date.desc())
                .limit(120)
            )
            prices = prices_res.all()
            
    if not prices:
        raise HTTPException(status_code=400, detail="No historical price data found or fetched for forecasting")
        
    price_df = pd.DataFrame(prices, columns=["date", "modal_price"])
    price_df = price_df.sort_values("date").reset_index(drop=True)
    
    # Fetch historical weather
    weather_res = await db.execute(
        select(WeatherObservation.date, WeatherObservation.temp_max, WeatherObservation.temp_min, WeatherObservation.precipitation_mm)
        .where(WeatherObservation.mandi_id == mandi.id)
        .order_by(WeatherObservation.date.desc())
        .limit(120)
    )
    weather = weather_res.all()
    weather_df = pd.DataFrame(weather, columns=["date", "temp_max", "temp_min", "precipitation_mm"])
    weather_df = weather_df.sort_values("date").reset_index(drop=True)
    
    # Merge and align historical data
    merged_history = pd.merge(price_df, weather_df, on="date", how="left")
    merged_history["temp_max"] = merged_history["temp_max"].ffill().bfill().fillna(30.0)
    merged_history["temp_min"] = merged_history["temp_min"].ffill().bfill().fillna(22.0)
    merged_history["precipitation_mm"] = merged_history["precipitation_mm"].fillna(0.0)
    
    # 4. Fetch future weather covariates
    future_weather = await fetch_future_weather(mandi.latitude, mandi.longitude, horizon)
    future_weather_df = pd.DataFrame(future_weather)
    
    # 5. Run Winning Model
    # Onion, Potato, Tomato use CHRONOS-2. Tur Dal uses NAIVE.
    model_winner = "chronos" if commodity_slug in ["onion", "potato", "tomato"] else "naive"
    
    forecast_dates = future_weather_df["date"].tolist()
    
    if model_winner == "chronos":
        # Lazy load Chronos-2 forecaster from application state
        if not hasattr(request.app.state, "chronos_forecaster"):
            print("Lazy loading Chronos2Forecaster...")
            from app.forecasting.chronos_forecaster import Chronos2Forecaster
            request.app.state.chronos_forecaster = Chronos2Forecaster()
        forecaster = request.app.state.chronos_forecaster
        forecasts = forecaster.forecast(
            history_df=merged_history,
            horizon=horizon,
            future_weather_df=future_weather_df
        )
        p10 = list(forecasts["p10"])
        p50 = list(forecasts["p50"])
        p90 = list(forecasts["p90"])
    else:
        # NAIVE baseline model
        last_price = float(merged_history["modal_price"].iloc[-1])
        # Standard deviation of differences for realistic confidence intervals
        std_diff = merged_history["modal_price"].diff().std()
        if pd.isna(std_diff) or std_diff == 0:
            std_diff = last_price * 0.05
            
        p50 = [last_price] * horizon
        p10 = [last_price - 1.645 * std_diff * np.sqrt(step) for step in range(1, horizon + 1)]
        p90 = [last_price + 1.645 * std_diff * np.sqrt(step) for step in range(1, horizon + 1)]
        
        # Clip intervals to be non-negative
        p10 = [max(0.0, float(v)) for v in p10]
        p90 = [max(0.0, float(v)) for v in p90]
        p50 = [float(v) for v in p50]
        
    # Construct response
    forecast_response = ForecastResponse(
        commodity=commodity.name,
        mandi=mandi.name,
        horizon=horizon,
        forecast_dates=forecast_dates,
        p10=p10,
        p50=p50,
        p90=p90,
        weather_covariates=[
            WeatherObservationOut(
                date=w["date"],
                temp_max=w["temp_max"],
                temp_min=w["temp_min"],
                precipitation_mm=w["precipitation_mm"]
            ) for w in future_weather
        ]
    )
    
    # Save to Redis Cache (24-hour TTL)
    try:
        await redis.setex(
            cache_key,
            timedelta(hours=24),
            json.dumps(forecast_response.model_dump(), default=str)
        )
    except Exception as e:
        print(f"Redis cache write error: {e}")
        
    # Trigger logging to DB in background
    background_tasks.add_task(
        log_forecast_to_db,
        commodity_id=commodity.id,
        mandi_id=mandi.id,
        forecast_dates=forecast_dates,
        p10=p10,
        p50=p50,
        p90=p90,
        model_name=model_winner
    )
        
    return forecast_response


@router.get("/accuracy/{commodity_slug}", response_model=List[ForecastAccuracyOut], tags=["Forecasting"])
async def get_accuracy(
    commodity_slug: str,
    horizon: int = 30,
    db: AsyncSession = Depends(get_db)
):
    """Fetch live accuracy records over time for a given commodity."""
    # Find commodity
    comm_res = await db.execute(select(Commodity).where(Commodity.slug == commodity_slug))
    commodity = comm_res.scalar_one_or_none()
    if not commodity:
        raise HTTPException(status_code=404, detail="Commodity not found")
        
    # Query accuracy observations
    accuracy_res = await db.execute(
        select(ForecastAccuracy)
        .where(ForecastAccuracy.commodity_id == commodity.id, ForecastAccuracy.horizon == horizon)
        .order_by(ForecastAccuracy.eval_date.desc())
        .limit(30) # Last 30 evaluation points
    )
    accuracy_list = accuracy_res.scalars().all()
    # Reverse to chronological order
    accuracy_list.reverse()
    
    return [ForecastAccuracyOut.model_validate(a) for a in accuracy_list]


class ChatRequest(BaseModel):
    question: str
    history_prices: List[dict]
    forecast_p50: List[float]
    forecast_dates: List[str]
    weather_covariates: List[dict]
    commodity: str
    mandi: str


@router.post("/chat", tags=["AI Advisor"])
async def chat_advisor(req: ChatRequest):
    """
    AI Chatbot Advisor: answers questions based on price/weather/forecast data context.
    Calls the OpenRouter API.
    """
    api_key = get_settings().OPENROUTER_API_KEY
    if not api_key or api_key == "your_openrouter_api_key_here" or api_key == "":
        raise HTTPException(status_code=400, detail="OpenRouter API Key not set or is placeholder. Please set OPENROUTER_API_KEY in backend/.env")
        
    # Prepare Context for the LLM
    context = (
        f"You are an expert agricultural advisor and commodity trader assistant for AgroPredict.\n"
        f"Provide actionable, specific insights for the commodity '{req.commodity}' at the '{req.mandi}' market.\n\n"
        f"--- CURRENT DATA ---\n"
        f"Historical Prices (last few observations):\n"
    )
    for p in req.history_prices[-10:]:
        context += f"- {p.get('date')}: ₹{p.get('modal_price')}/Qtl\n"
        
    context += f"\nForecasted Prices (p50 median forecast):\n"
    for d, p in zip(req.forecast_dates[:15], req.forecast_p50[:15]):
        context += f"- {d}: ₹{p}/Qtl\n"
        
    context += f"\nWeather Forecast (precipitation and temperature max/min):\n"
    for w in req.weather_covariates[:7]:
        context += f"- {w.get('date')}: Max Temp {w.get('temp_max')}C, Min Temp {w.get('temp_min')}C, Rain {w.get('precipitation_mm')}mm\n"
        
    context += (
        f"\nAnswer the following question from the user based on the data above. "
        f"Keep your answers concise, practical, and highly relevant for farmers or traders. "
        f"Structure your response with bullet points if helpful."
    )
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://agropredict.local",
        "X-Title": "AgroPredict Dashboard",
    }
    
    payload = {
        "model": "meta-llama/llama-3-8b-instruct:free",
        "messages": [
            {"role": "system", "content": context},
            {"role": "user", "content": req.question}
        ]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30.0)
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=f"OpenRouter API error: {resp.text}")
            res_data = resp.json()
            reply = res_data["choices"][0]["message"]["content"]
            return {"reply": reply}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LLM request failed: {e}")


def hash_password(password: str) -> str:
    import hashlib
    import os
    salt = os.urandom(16)
    pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + pw_hash.hex()


def verify_password(password: str, hashed: str) -> bool:
    import hashlib
    try:
        salt_hex, hash_hex = hashed.split(":")
        salt = bytes.fromhex(salt_hex)
        pw_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
        return pw_hash.hex() == hash_hex
    except Exception:
        return False


class RegisterRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class SavedQueryOut(BaseModel):
    id: int
    commodity_slug: str
    mandi_name: str
    state: str
    district: str
    start_date: str
    end_date: str
    created_at: str

    class Config:
        from_attributes = True


class LogQueryRequest(BaseModel):
    commodity_slug: str
    mandi_name: str
    state: str
    district: str
    start_date: str
    end_date: str


@router.post("/auth/register", tags=["Auth"])
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    # Check if username exists
    res = await db.execute(select(User).where(User.username == req.username))
    existing = res.scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    pw_hash = hash_password(req.password)
    user = User(username=req.username, password_hash=pw_hash)
    db.add(user)
    await db.commit()
    return {"status": "success", "message": "User registered successfully"}


@router.post("/auth/login", tags=["Auth"])
async def login(req: LoginRequest, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(User).where(User.username == req.username))
    user = res.scalar_one_or_none()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid username or password")
        
    # Return simple session info (user_id and username)
    return {"status": "success", "user_id": user.id, "username": user.username}


@router.post("/users/{user_id}/logs", tags=["Auth"])
async def log_user_query(user_id: int, req: LogQueryRequest, db: AsyncSession = Depends(get_db)):
    # Validate user
    res = await db.execute(select(User).where(User.id == user_id))
    user = res.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    # Log query
    log_entry = UserQueryLog(
        user_id=user_id,
        commodity_slug=req.commodity_slug,
        mandi_name=req.mandi_name,
        state=req.state,
        district=req.district,
        start_date=date.fromisoformat(req.start_date),
        end_date=date.fromisoformat(req.end_date),
        created_at=datetime.now()
    )
    db.add(log_entry)
    await db.commit()
    return {"status": "success"}


@router.get("/users/{user_id}/logs", response_model=List[SavedQueryOut], tags=["Auth"])
async def get_user_query_logs(user_id: int, db: AsyncSession = Depends(get_db)):
    # Fetch last 20 logs
    res = await db.execute(
        select(UserQueryLog)
        .where(UserQueryLog.user_id == user_id)
        .order_by(UserQueryLog.created_at.desc())
        .limit(20)
    )
    logs = res.scalars().all()
    return [
        SavedQueryOut(
            id=l.id,
            commodity_slug=l.commodity_slug,
            mandi_name=l.mandi_name,
            state=l.state,
            district=l.district,
            start_date=l.start_date.isoformat(),
            end_date=l.end_date.isoformat(),
            created_at=l.created_at.isoformat()
        ) for l in logs
    ]


