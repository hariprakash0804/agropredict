import uvicorn
import gradio as gr
import spaces
from app.main import app

# 1. Define a dummy function decorated with @spaces.GPU for Hugging Face ZeroGPU validation
@spaces.GPU
def dummy_gpu_trigger(x):
    return x

# 2. Create a minimal Gradio blocks interface that hooks up the GPU function
with gr.Blocks() as demo:
    gr.Markdown("# AgroPredict API Gateway")
    # A hidden button pointing to the GPU function to register it in the event loop
    btn = gr.Button("Init", visible=False)
    btn.click(dummy_gpu_trigger, inputs=None, outputs=None)

# 3. Mount Gradio onto our FastAPI application at the "/dashboard" path
# This keeps all our existing FastAPI "/api/..." endpoints perfectly intact at the root "/"
app = gr.mount_gradio_app(app, demo, path="/dashboard")

if __name__ == "__main__":
    # Hugging Face Spaces expects the app to run on port 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
