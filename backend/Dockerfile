FROM python:3.10.16-slim
WORKDIR /app
COPY backend/requirements.in /tmp/requirements.in
RUN pip install --no-cache-dir -r /tmp/requirements.in
COPY backend /app/backend
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
