# Small, current Python base image.
FROM python:3.12-slim

# Don't write .pyc files, and flush logs immediately.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first so Docker can cache this layer.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code and the web page.
COPY app.py .
COPY frontend/ ./frontend/

# The API key is NOT copied or set here. It is passed in at run time.
EXPOSE 8000

# Start the server. 0.0.0.0 makes it reachable from outside the container.
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
