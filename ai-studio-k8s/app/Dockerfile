# Small, current Python base image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so this layer is cached.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code and web UI.
COPY app.py .
COPY frontend/ ./frontend/

# The API key is NOT set here. It comes from a Kubernetes Secret at run time.
EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
