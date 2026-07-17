# 1. Hotfix: Inject mock HfFolder into huggingface_hub to solve the Gradio import error
import huggingface_hub
if not hasattr(huggingface_hub, "HfFolder"):
    class MockHfFolder:
        @staticmethod
        def get_token():
            return None
        @staticmethod
        def save_token(token):
            pass
        @staticmethod
        def delete_token():
            pass
    huggingface_hub.HfFolder = MockHfFolder

import uvicorn
import gradio as gr
from app.main import app

# 2. Create a minimal Gradio blocks interface to satisfy ZeroGPU supervisor requirements
with gr.Blocks() as demo:
    gr.Markdown("# 🌾 AgroPredict API Gateway")
    gr.Markdown("The AgroPredict Price Forecasting Service is running. Access API documentation at `/docs`.")

# 3. Mount Gradio onto our FastAPI application at the "/dashboard" path
# This keeps all our existing FastAPI "/api/..." endpoints perfectly intact at the root "/"
app = gr.mount_gradio_app(app, demo, path="/dashboard")

if __name__ == "__main__":
    # Hugging Face Spaces expects the app to run on port 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
