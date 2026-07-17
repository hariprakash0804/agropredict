import uvicorn
import spaces
from app.main import app

# ZeroGPU mandatory startup decorator check bypass
@spaces.GPU
def dummy_gpu_trigger():
    print("Hugging Face ZeroGPU context initialized.")

# Run the dummy function on file import
dummy_gpu_trigger()

if __name__ == "__main__":
    # Hugging Face Spaces expects the app to run on port 7860
    uvicorn.run(app, host="0.0.0.0", port=7860)
