# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install minimal OS utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code and validated AI model artifacts
COPY src/ /app/src/
COPY models/stage5/ /app/models/stage5/

# Create directory for runtime storage
RUN mkdir -p /data /tmp

# Runtime environment configuration
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/src
ENV DTN_ENV=production
ENV DTN_DB_PATH=/tmp/demo_system.db
ENV PORT=8000

EXPOSE 8000

# Start FastAPI server binding to 0.0.0.0 using dynamic cloud PORT
CMD ["sh", "-c", "uvicorn api.server:app --host 0.0.0.0 --port ${PORT:-8000}"]

