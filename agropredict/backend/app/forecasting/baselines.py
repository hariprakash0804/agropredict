"""
AgroPredict - Baseline Forecasters

Includes:
1. NaiveForecaster: Forecasts using the last observed value.
2. SeasonalNaiveForecaster: Forecasts using the value from the same day-of-week 7 days ago.
3. LightGBMForecaster: Features lagged prices, rolling averages, calendar effects, and weather covariates.
"""
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from typing import Dict, Any, List

class NaiveForecaster:
    """Forecasts = last observed value."""
    def forecast(self, history: pd.Series, horizon: int) -> np.ndarray:
        if history.empty:
            return np.zeros(horizon)
        last_val = history.iloc[-1]
        return np.full(horizon, last_val, dtype=float)


class SeasonalNaiveForecaster:
    """Forecasts = value from N days ago (e.g. 7 days for weekly seasonality)."""
    def __init__(self, seasonal_period: int = 7):
        self.seasonal_period = seasonal_period

    def forecast(self, history: pd.Series, horizon: int) -> np.ndarray:
        if len(history) < self.seasonal_period:
            # Fallback to naive if not enough history
            last_val = history.iloc[-1] if not history.empty else 0.0
            return np.full(horizon, last_val, dtype=float)
            
        forecast_vals = []
        for i in range(horizon):
            # Map index back into history
            back_idx = len(history) - self.seasonal_period + (i % self.seasonal_period)
            if back_idx >= 0 and back_idx < len(history):
                forecast_vals.append(history.iloc[back_idx])
            else:
                forecast_vals.append(history.iloc[-1])
        return np.array(forecast_vals, dtype=float)


class LightGBMForecaster:
    """
    LightGBM regressor utilizing lagged prices, rolling statistics, calendar,
    and weather covariates. Matches multi-step forecasts using a recursive
    or direct strategy.
    
    We build ONE model per commodity because Onion, Potato, Tomato, and Tur Dal
    have very different price dynamics, seasonality scales, and production locations.
    A single model containing commodity as a categorical feature can often underperform
    on localized shocks compared to dedicated per-commodity models.
    """
    def __init__(self, horizon: int = 30):
        self.horizon = horizon
        self.models = {}  # Store a model for each step in the horizon (direct forecasting)

    def _create_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Creates features from a DataFrame containing 'modal_price', weather, and date columns.
        Expected columns in df: ['date', 'modal_price', 'temp_max', 'temp_min', 'precipitation_mm']
        """
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date').reset_index(drop=True)
        
        # Calendar features
        df['day_of_week'] = df['date'].dt.dayofweek
        df['month'] = df['date'].dt.month
        
        # Target lags
        for lag in [1, 2, 3, 7]:
            df[f'price_lag_{lag}'] = df['modal_price'].shift(lag).bfill().ffill()
            
        # Target rolling statistics
        for window in [3, 7]:
            df[f'price_roll_mean_{window}'] = df['modal_price'].shift(1).rolling(window, min_periods=1).mean().bfill().ffill()
            df[f'price_roll_std_{window}'] = df['modal_price'].shift(1).rolling(window, min_periods=1).std().fillna(0.0)

        # Weather features
        df['temp_range'] = df['temp_max'] - df['temp_min']
        df['precip_roll_sum_7'] = df['precipitation_mm'].rolling(7, min_periods=1).sum()
        df['precip_roll_sum_30'] = df['precipitation_mm'].rolling(30, min_periods=1).sum()
        
        return df

    def fit(self, train_df: pd.DataFrame):
        """
        Fits a direct multi-step LightGBM model.
        train_df must contain: ['date', 'modal_price', 'temp_max', 'temp_min', 'precipitation_mm']
        """
        fe_df = self._create_features(train_df)
        
        # Define base feature columns
        feature_cols = [
            'day_of_week', 'month', 'temp_max', 'temp_min', 'precipitation_mm',
            'temp_range', 'precip_roll_sum_7', 'precip_roll_sum_30',
            'price_lag_1', 'price_lag_2', 'price_lag_3', 'price_lag_7',
            'price_roll_mean_3', 'price_roll_mean_7',
            'price_roll_std_3', 'price_roll_std_7'
        ]
        
        # Train a separate model for each step ahead (direct multi-step)
        for h in range(1, self.horizon + 1):
            # Target is the price shifted forward by h steps
            y = fe_df['modal_price'].shift(-h)
            X = fe_df[feature_cols].copy()
            
            # Remove rows with NaN target or NaN features
            valid_idx = X.notna().all(axis=1) & y.notna()
            X_clean = X[valid_idx]
            y_clean = y[valid_idx]
            
            if len(X_clean) < 3:
                # Too little data, skip fitting this step (will fallback to linear momentum projection)
                continue
                
            model = LGBMRegressor(
                n_estimators=50,
                learning_rate=0.05,
                max_depth=4,
                num_leaves=15,
                random_state=42,
                verbosity=-1
            )
            model.fit(X_clean, y_clean)
            self.models[h] = (model, feature_cols)

    def forecast(self, history_df: pd.DataFrame) -> np.ndarray:
        """
        Forecast the next `horizon` days.
        history_df must contain the latest records to construct features for the forecast origin.
        """
        fe_df = self._create_features(history_df)
        # We take the very last row as our forecast origin
        origin_row = fe_df.iloc[[-1]]
        
        forecast_vals = []
        last_valid_val = history_df['modal_price'].iloc[-1]
        
        for h in range(1, self.horizon + 1):
            if h in self.models:
                model, feature_cols = self.models[h]
                X = origin_row[feature_cols]
                # If there are NaNs in features, fill with defaults/last value
                if X.isna().any().any():
                    pred = last_valid_val
                else:
                    pred = model.predict(X)[0]
            else:
                # Fallback to the last available forecast or history value
                pred = forecast_vals[-1] if forecast_vals else last_valid_val
            
            # Make sure it's non-negative
            pred = max(0.0, float(pred))
            forecast_vals.append(pred)
            
        return np.array(forecast_vals)
