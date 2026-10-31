FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
RUN mkdir -p data

# Non-root user; DuckDB lives in /app/data (snapshotted to Postgres when DATABASE_URL is set).
RUN useradd --create-home hive && chown -R hive /app
USER hive

EXPOSE 8000
# Render (and others) pass the port in $PORT; 8000 locally.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips '*'"]
