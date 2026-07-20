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

import gradio as gr
import spaces
from app.main import app

# 2. Define a dummy function decorated with @spaces.GPU at the top level of app.py
@spaces.GPU
def dummy_gpu_trigger(x):
    return x

# 3. Create a minimal Gradio blocks interface to satisfy ZeroGPU supervisor requirements
with gr.Blocks() as demo:
    gr.Markdown("# 🌾 AgroPredict API Gateway")
    gr.Markdown("The AgroPredict Price Forecasting Service is running. Access API documentation at `/docs`.")
    # A dummy input and output to register the GPU function with Gradio Blocks
    inp = gr.Textbox(visible=False)
    out = gr.Textbox(visible=False)
    btn = gr.Button("Init", visible=False)
    btn.click(dummy_gpu_trigger, inputs=inp, outputs=out)

# 4. Mount our FastAPI app onto Gradio's internal FastAPI app at the root prefix "/"
# This preserves all "/api/..." path prefixes correctly for routing
demo.app.mount("/", app)

if __name__ == "__main__":
    # Launch Gradio natively on port 7860 (satisfying HF ZeroGPU supervisor)
    demo.launch(server_name="0.0.0.0", server_port=7860)
