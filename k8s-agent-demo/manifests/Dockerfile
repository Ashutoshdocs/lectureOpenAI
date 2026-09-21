FROM python:3.12-slim
WORKDIR /app
COPY app.py .
# App reads LOG_LEVEL / PORT from the environment at startup.
CMD ["python", "app.py"]
