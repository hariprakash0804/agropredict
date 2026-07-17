"""
AgroPredict - Chronos-2 Forecaster

Implements Amazon Chronos-2 foundation model forecasting with native covariate support.
Loads model dynamically from configuration.
"""
import numpy as np
import pandas as pd
import torch
from typing import Dict, Any, Tuple

from app.core.config import get_settings
# pyrefly: ignore [missing-import]
from chronos import Chronos2Pipeline
# pyrefly: ignore [missing-import]
from chronos.chronos2.preprocess import from_data_frame

settings = get_settings()

class Chronos2Forecaster:
    """
    Forecaster using Amazon Chronos-2 pre-trained model.
    Supports probabilistic quantile outputs (p10, p50, p90) and future weather covariates.
    """
    def __init__(self, model_name: str = None):
        self.model_name = model_name or settings.CHRONOS_MODEL_NAME
        print(f"Loading Chronos-2 Pipeline from: {self.model_name}...")
        self.pipeline = Chronos2Pipeline.from_pretrained(
            self.model_name,
            device_map="cpu",
            torch_dtype=torch.bfloat16
        )
        # Identify indices for key quantiles
        self.q_indices = {
            "p10": self.pipeline.quantiles.index(0.1),
            "p50": self.pipeline.quantiles.index(0.5),
            "p90": self.pipeline.quantiles.index(0.9),
        }

    def forecast(
        self,
        history_df: pd.DataFrame,
        horizon: int,
        future_weather_df: pd.DataFrame
    ) -> Dict[str, np.ndarray]:
        """
        Generates quantile forecasts for the given horizon.
        
        history_df columns: ['date', 'modal_price', 'temp_max', 'temp_min', 'precipitation_mm']
        future_weather_df columns: ['date', 'temp_max', 'temp_min', 'precipitation_mm']
        
        Returns:
            Dict containing arrays for 'p10', 'p50', and 'p90' predictions.
        """
        # Prepare inputs according to Chronos-2 requirements
        df = history_df.copy()
        df = df.rename(columns={"date": "timestamp"})
        df["item_id"] = "commodity_mandi"
        
        # Prepare future df
        f_df = future_weather_df.copy()
        f_df = f_df.rename(columns={"date": "timestamp"})
        f_df["item_id"] = "commodity_mandi"
        # Dummy price column to satisfy schema
        f_df["modal_price"] = np.nan
        
        # We need target columns + covariates columns
        # To avoid mismatch, we select only the columns that exist in both dfs
        common_cols = ["timestamp", "item_id", "temp_max", "temp_min", "precipitation_mm"]
        
        # Sort and prep
        df = df[common_cols + ["modal_price"]].sort_values("timestamp").reset_index(drop=True)
        f_df = f_df[common_cols].sort_values("timestamp").reset_index(drop=True)
        
        # Chronos-2 preprocess input builder
        inputs = from_data_frame(
            df=df,
            target_columns=["modal_price"],
            prediction_length=horizon,
            future_df=f_df
        )
        
        # Run inference
        with torch.no_grad():
            predictions = self.pipeline.predict(inputs, prediction_length=horizon)
            
        # Extract forecast tensor: shape (1, num_quantiles, horizon)
        forecast_tensor = predictions[0]
        
        # Map indices to arrays
        p10 = forecast_tensor[0, self.q_indices["p10"]].numpy()
        p50 = forecast_tensor[0, self.q_indices["p50"]].numpy()
        p90 = forecast_tensor[0, self.q_indices["p90"]].numpy()
        
        # Ensure values are non-negative
        p10 = np.clip(p10, 0, None)
        p50 = np.clip(p50, 0, None)
        p90 = np.clip(p90, 0, None)
        
        return {
            "p10": p10,
            "p50": p50,
            "p90": p90
        }
