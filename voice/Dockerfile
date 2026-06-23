FROM python:3.11-slim

# System deps for ChromaDB, audio processing, and onnxruntime (Silero VAD)
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ libffi-dev libssl-dev curl

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . ./voice/

# Data directories created at runtime via env vars, but ensure /data exists
RUN mkdir -p /data/chromadb /data/notes

EXPOSE 8000

CMD ["uvicorn", "voice.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
