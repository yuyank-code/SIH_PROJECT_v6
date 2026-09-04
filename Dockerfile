FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

# Deliberately invalidate the backend source layer after source corrections.
ARG BACKEND_SOURCE_REV=20260830-02
COPY backend /app/backend
RUN python -m py_compile /app/backend/server.py

COPY model /app/model

WORKDIR /app/backend

EXPOSE 10000
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-10000}"]
