"""
AgroPredict - Live Accuracy Evaluation Script

Retrospectively matches logged forecasts with actual observed commodity prices
to compute MAE, RMSE, and MAPE. Inserts results into the forecast_accuracies table.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date, timedelta
import numpy as np
import pandas as pd
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, select, func
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker
# pyrefly: ignore [missing-import]
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app.core.config import get_settings
from app.models.commodity import Commodity, Mandi, PriceObservation, ForecastLog, ForecastAccuracy

def compute_metrics(y_true: float, y_pred: float) -> tuple[float, float, float]:
    """Calculate error metrics for a single observation pair."""
    mae = abs(y_true - y_pred)
    rmse = (y_true - y_pred) ** 2  # Will be square-rooted after averaging
    mape = (abs(y_true - y_pred) / y_true) * 100 if y_true != 0 else 0.0
    return mae, rmse, mape

def evaluate_accuracy():
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    try:
        print("Starting scheduled live accuracy evaluation...")
        
        # We find all unique combinations of (commodity_id, mandi_id, model_name, forecast_date) in logs
        # that have an actual price observation in database
        logs_q = db.execute(
            select(
                ForecastLog.commodity_id,
                ForecastLog.mandi_id,
                ForecastLog.model_name,
                ForecastLog.forecast_date,
                ForecastLog.p50,
                PriceObservation.modal_price
            )
            .join(
                PriceObservation,
                (ForecastLog.commodity_id == PriceObservation.commodity_id) &
                (ForecastLog.mandi_id == PriceObservation.mandi_id) &
                (ForecastLog.forecast_date == PriceObservation.date)
            )
        ).all()
        
        if not logs_q:
            print("No logged forecasts found with corresponding actual price observations.")
            return
            
        print(f"Found {len(logs_q)} evaluation pairs. Processing...")
        
        # Group by (commodity_id, mandi_id, model_name, eval_date) to calculate metrics
        # We can evaluate on a daily rolling basis or weekly average.
        # Let's insert daily tracking records.
        inserted = 0
        for row in logs_q:
            comm_id, mandi_id, model_name, f_date, p50, actual = row
            
            # Simple daily point metrics
            mae, rmse_sq, mape = compute_metrics(actual, p50)
            rmse = np.sqrt(rmse_sq)
            
            # Determine horizon: we can calculate based on created_at in logs
            # Let's query log created_at date
            created_at_q = db.execute(
                select(ForecastLog.created_at)
                .where(
                    ForecastLog.commodity_id == comm_id,
                    ForecastLog.mandi_id == mandi_id,
                    ForecastLog.model_name == model_name,
                    ForecastLog.forecast_date == f_date
                )
                .limit(1)
            ).scalar()
            
            horizon = 30
            if created_at_q:
                horizon = (f_date - created_at_q.date()).days
                # Normalize horizon to 7 or 30 days
                horizon = 7 if horizon <= 7 else 30
                
            stmt = mysql_insert(ForecastAccuracy).values(
                commodity_id=comm_id,
                mandi_id=mandi_id,
                eval_date=f_date,
                model_name=model_name,
                horizon=horizon,
                mae=mae,
                rmse=rmse,
                mape=mape
            ).on_duplicate_key_update(
                mae=mae,
                rmse=rmse,
                mape=mape
            )
            db.execute(stmt)
            inserted += 1
            
        db.commit()
        print(f"Accuracy evaluation complete. Inserted/updated {inserted} daily accuracy metrics.")
        
    finally:
        db.close()
        engine.dispose()

if __name__ == "__main__":
    evaluate_accuracy()
