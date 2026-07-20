"""
AgroPredict - Pydantic schemas for API requests and responses.
"""
from datetime import date
from typing import List, Optional, Dict
from pydantic import BaseModel


class CommodityOut(BaseModel):
    id: int
    name: str
    slug: str

    class Config:
        from_attributes = True


class MandiOut(BaseModel):
    id: int
    name: str
    state: str
    district: str
    latitude: float
    longitude: float

    class Config:
        from_attributes = True


class PriceObservationOut(BaseModel):
    date: date
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    modal_price: Optional[float] = None
    arrival_qty: Optional[float] = None
    variety: Optional[str] = "FAQ"
    grade: Optional[str] = "FAQ"

    class Config:
        from_attributes = True


class WeatherObservationOut(BaseModel):
    date: date
    temp_max: Optional[float] = None
    temp_min: Optional[float] = None
    precipitation_mm: Optional[float] = None

    class Config:
        from_attributes = True


class ForecastResponse(BaseModel):
    commodity: str
    mandi: str
    horizon: int
    forecast_dates: List[date]
    p10: List[float]
    p50: List[float]
    p90: List[float]
    weather_covariates: List[WeatherObservationOut]
    variety: str = "FAQ"
    grade: str = "FAQ"
    
    # AI generated fields (with default/heuristic fallbacks)
    farmer_strategy: str = "Sell Immediately (Prevent Losses)"
    farmer_advisory: str = "Prices are expected to decline. Selling your harvest now secures the current modal rate."
    trader_strategy: str = "Procure Spot Market"
    trader_advisory: str = "Prices are trending down. Spot buying matches daily demand cycles best without locking high contract rates."
    rainfall_disruption_risk: str = "Minimal"
    heat_stress_risk: str = "Low"


class HistoryResponse(BaseModel):
    commodity: str
    mandi: str
    prices: List[PriceObservationOut]
    weather: List[WeatherObservationOut]


class ForecastAccuracyOut(BaseModel):
    eval_date: date
    model_name: str
    horizon: int
    mae: float
    rmse: float
    mape: float

    class Config:
        from_attributes = True

