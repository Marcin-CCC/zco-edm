FROM python:3.11-slim

WORKDIR /app

# Instalacja zaleZNOSCI systemowych (w tym curl dla healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Kopiowanie zaleZNOSCI
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiowanie kodu
COPY ./app /app/app

# Port FastAPI
EXPOSE 8000

# HEALTHCHECK
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -sf http://localhost:8000/api/health || exit 1

# Uruchomienie (bez --reload w produkcji)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]