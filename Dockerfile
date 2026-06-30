FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY config ./config
COPY sql ./sql
COPY static ./static
COPY templates ./templates

EXPOSE 8000

CMD exec uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT:-8000}
