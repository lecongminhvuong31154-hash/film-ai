# Single-origin deployment: FastAPI serves React UI + API + protected media.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=10000
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY frontend/dist ./frontend/dist
COPY assets ./assets
RUN mkdir -p /app/runtime_data
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers"]
