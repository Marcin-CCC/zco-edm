FROM nvcr.io/nvidia/pytorch:25.01-py3

WORKDIR /app

# Instalacja zalezności Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Kopiowanie kodu
COPY main.py /app/main.py

# Port
EXPOSE 8000

# Uruchomienie
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]