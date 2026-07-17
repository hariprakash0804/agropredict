"""
AgroPredict - Backtesting Harness

Performs expanding-window rolling-origin backtesting over historical data
and evaluates baselines (Naive, Seasonal Naive, LightGBM) and primary models.
"""
import os
import sys
import subprocess
from datetime import datetime, date, timedelta
import numpy as np
import pandas as pd
from typing import List, Dict, Any, Tuple
# pyrefly: ignore [missing-import]
from sqlalchemy import create_engine, select
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import sessionmaker

from pathlib import Path

# Add backend directory to Python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent if '__file__' in locals() else '.'))

from app.core.config import get_settings
from app.models.commodity import Commodity, Mandi, PriceObservation, WeatherObservation
from app.forecasting.baselines import NaiveForecaster, SeasonalNaiveForecaster, LightGBMForecaster
from app.forecasting.chronos_forecaster import Chronos2Forecaster

def get_git_revision_hash() -> str:
    """Gets the current git commit hash."""
    try:
        return subprocess.check_output(['git', 'rev-parse', 'HEAD'], stderr=subprocess.DEVNULL).decode('ascii').strip()
    except Exception:
        return "N/A (Git not initialized/installed)"

def get_historical_data(db_session, commodity_slug: str, mandi_id: int) -> pd.DataFrame:
    """
    Fetch historical prices and weather covariates aligned by date.
    """
    # Fetch commodity
    comm = db_session.execute(
        select(Commodity).where(Commodity.slug == commodity_slug)
    ).scalar_one()
    
    # Fetch price observations
    price_q = db_session.execute(
        select(PriceObservation.date, PriceObservation.modal_price)
        .where(PriceObservation.commodity_id == comm.id, PriceObservation.mandi_id == mandi_id)
        .order_by(PriceObservation.date)
    ).all()
    
    price_df = pd.DataFrame(price_q, columns=["date", "modal_price"])
    if price_df.empty:
        return pd.DataFrame()
        
    # Fetch weather observations
    weather_q = db_session.execute(
        select(WeatherObservation.date, WeatherObservation.temp_max, WeatherObservation.temp_min, WeatherObservation.precipitation_mm)
        .where(WeatherObservation.mandi_id == mandi_id)
        .order_by(WeatherObservation.date)
    ).all()
    
    weather_df = pd.DataFrame(weather_q, columns=["date", "temp_max", "temp_min", "precipitation_mm"])
    
    # Merge on date
    merged = pd.merge(price_df, weather_df, on="date", how="left")
    merged = merged.sort_values("date").reset_index(drop=True)
    
    # Fill any missing weather values with defaults
    merged["temp_max"] = merged["temp_max"].ffill().bfill().fillna(30.0)
    merged["temp_min"] = merged["temp_min"].ffill().bfill().fillna(22.0)
    merged["precipitation_mm"] = merged["precipitation_mm"].fillna(0.0)
    
    return merged

def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray) -> Tuple[float, float, float]:
    """Computes MAE, RMSE, and MAPE."""
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    
    # Avoid division by zero in MAPE
    mask = y_true != 0
    if np.any(mask):
        mape = np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100
    else:
        mape = 0.0
        
    return float(mae), float(rmse), float(mape)

def run_backtest(models_to_test: List[str] = ["naive", "seasonal_naive", "lightgbm", "chronos"]) -> Dict[str, Any]:
    settings = get_settings()
    engine = create_engine(settings.SYNC_DATABASE_URL, echo=False)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    
    results = {}
    
    # Initialize Chronos forecaster once (heavy weight loading)
    chronos_forecaster = None
    if "chronos" in models_to_test:
        chronos_forecaster = Chronos2Forecaster()
    
    try:
        commodities = db.execute(select(Commodity)).scalars().all()
        mandis = db.execute(select(Mandi)).scalars().all()
        
        horizon = 30 # Backtest up to 30 days ahead
        num_folds = 8
        
        for comm in commodities:
            results[comm.slug] = {}
            for mandi in mandis:
                df = get_historical_data(db, comm.slug, mandi.id)
                if df.empty or len(df) < 180: # Need at least ~6 months to backtest properly
                    print(f"Skipping {comm.name} in {mandi.name} (insufficient data: {len(df)} rows)")
                    continue
                
                print(f"Backtesting {comm.name} at {mandi.name} ({len(df)} records)...")
                
                # Folds calculation
                # We evaluate forecast accuracy on rolling origins
                # Fold step size is 14 days
                fold_step = 14
                total_len = len(df)
                
                fold_results = {model: [] for model in models_to_test}
                
                for fold in range(num_folds):
                    # We start backwards from the end
                    # Origin index for the forecast
                    origin_idx = total_len - horizon - (fold * fold_step)
                    if origin_idx < 120:  # Need at least 120 days of training data
                        break
                        
                    train_data = df.iloc[:origin_idx].copy()
                    test_data = df.iloc[origin_idx:origin_idx + horizon].copy()
                    
                    y_true = test_data["modal_price"].values
                    
                    # 1. Naive model
                    if "naive" in models_to_test:
                        forecaster = NaiveForecaster()
                        pred = forecaster.forecast(train_data["modal_price"], horizon)
                        metrics = compute_metrics(y_true, pred)
                        fold_results["naive"].append(metrics)
                        
                    # 2. Seasonal Naive model
                    if "seasonal_naive" in models_to_test:
                        forecaster = SeasonalNaiveForecaster(seasonal_period=7)
                        pred = forecaster.forecast(train_data["modal_price"], horizon)
                        metrics = compute_metrics(y_true, pred)
                        fold_results["seasonal_naive"].append(metrics)
                        
                    # 3. LightGBM model
                    if "lightgbm" in models_to_test:
                        forecaster = LightGBMForecaster(horizon=horizon)
                        # Train on historical features
                        forecaster.fit(train_data)
                        # Predict next 30 days
                        pred = forecaster.forecast(train_data)
                        metrics = compute_metrics(y_true, pred)
                        fold_results["lightgbm"].append(metrics)
                        
                    # 4. Chronos model
                    if "chronos" in models_to_test and chronos_forecaster is not None:
                        future_weather = test_data[['date', 'temp_max', 'temp_min', 'precipitation_mm']].copy()
                        forecasts_dict = chronos_forecaster.forecast(
                            history_df=train_data,
                            horizon=horizon,
                            future_weather_df=future_weather
                        )
                        pred = forecasts_dict["p50"]
                        metrics = compute_metrics(y_true, pred)
                        fold_results["chronos"].append(metrics)
                
                results[comm.slug][mandi.name] = fold_results
                
    finally:
        db.close()
        engine.dispose()
        
    return results

def generate_markdown_report(results: Dict[str, Any], models_tested: List[str]):
    """
    Format and write backtest results to docs/BACKTEST_RESULTS.md.
    """
    git_hash = get_git_revision_hash()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    lines = [
        "# AgroPredict — Backtest Results",
        "",
        f"**Generated At**: {timestamp}  ",
        f"**Git Commit Hash**: `{git_hash}`  ",
        "",
        "This report lists the performance metrics (MAE, RMSE, MAPE) evaluated across 8 expanding-window rolling-origins.",
        "Horizon is 30 days ahead.",
        "",
        "## Summary Metrics",
        ""
    ]
    
    # Table header
    lines.append("| Commodity | Mandi | Model | MAE | RMSE | MAPE (%) |")
    lines.append("|---|---|---|---|---|---|")
    
    for comm_slug, mandi_data in results.items():
        for mandi_name, model_data in mandi_data.items():
            for model_name in models_tested:
                folds = model_data.get(model_name, [])
                if not folds:
                    continue
                # Average metrics over all folds
                maes = [f[0] for f in folds]
                rmses = [f[1] for f in folds]
                mapes = [f[2] for f in folds]
                
                avg_mae = np.mean(maes)
                avg_rmse = np.mean(rmses)
                avg_mape = np.mean(mapes)
                
                lines.append(
                    f"| {comm_slug.capitalize()} | {mandi_name} | {model_name.upper()} "
                    f"| {avg_mae:.2f} | {avg_rmse:.2f} | {avg_mape:.2f}% |"
                )
                
    lines.append("")
    lines.append("## Detailed Per-Fold Variance (Sample fold for Onion - Singanallur)")
    lines.append("")
    lines.append("| Fold | Model | MAE | RMSE | MAPE (%) |")
    lines.append("|---|---|---|---|---|")
    
    # Output fold metrics for a sample
    if "onion" in results and "Singanallur" in results["onion"]:
        onion_sng = results["onion"]["Singanallur"]
        for model in models_tested:
            folds = onion_sng.get(model, [])
            for f_idx, fold_metrics in enumerate(folds):
                lines.append(
                    f"| Fold {f_idx+1} | {model.upper()} | {fold_metrics[0]:.2f} "
                    f"| {fold_metrics[1]:.2f} | {fold_metrics[2]:.2f}% |"
                )
                
    report_content = "\n".join(lines)
    
    # Ensure directory exists
    report_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../docs"))
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "BACKTEST_RESULTS.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"Report written to {report_path}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Run rolling-origin backtests")
    parser.add_argument(
        "--models",
        type=str,
        default="naive,seasonal_naive,lightgbm,chronos",
        help="Comma-separated list of models to backtest"
    )
    args = parser.parse_args()
    
    models = [m.strip() for m in args.models.split(",")]
    
    print("=" * 60)
    print("AgroPredict Backtesting Run")
    print(f"Models: {models}")
    print("=" * 60)
    
    results = run_backtest(models)
    generate_markdown_report(results, models)

if __name__ == "__main__":
    main()
