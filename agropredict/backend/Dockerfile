# Use official Python lightweight image
FROM python:3.10-slim

# Set work directory
WORKDIR /app

# Install system dependencies (needed for compiling certain MySQL/Redis packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install dependencies (CPU-only PyTorch to minimize container size)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy all application code
COPY . .

# Set up user permissions for Hugging Face Spaces (UID 1000)
RUN useradd -m -u 1000 user
USER user

# Set environment variables for huggingface Cache
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface

# Create Hugging Face cache directory with correct permissions
RUN mkdir -p /home/user/.cache/huggingface

# Expose Hugging Face Space default port
EXPOSE 7860

# Command to run uvicorn on Hugging Face default port 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
