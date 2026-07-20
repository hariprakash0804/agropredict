import uvicorn
# 1. Force import Chronos2Forecaster to register its @spaces.GPU decorator with the ZeroGPU daemon at startup
from app.forecasting.chronos_forecaster import Chronos2Forecaster
# 2. Import main FastAPI application
from app.main import app

if __name__ == "__main__":
    # Hugging Face Spaces expects the app to run on port 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
