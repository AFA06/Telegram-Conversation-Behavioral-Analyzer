# Multi-stage build: frontend (Vite/React) + backend (FastAPI) served as
# one image, one process, one Railway service — the API serves the built
# dashboard as static files (see app/main.py) and, when RUN_BOT_IN_PROCESS
# is set, also runs the Telegram bot's polling loop in the same process so
# it shares the same per-tenant SQLite files under /app/data.

FROM node:20-slim AS frontend-builder
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS backend
WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
COPY backend/bot/requirements.txt ./bot-requirements.txt
RUN pip install --no-cache-dir -r requirements.txt -r bot-requirements.txt

COPY backend/ ./
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

ENV PYTHONUNBUFFERED=1 \
    DATABASE_URL=sqlite:////app/data/analyzer.db \
    TENANT_DB_DIR=/app/data/tenants

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
