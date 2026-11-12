FROM node:24-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 REQUIRE_JWT_SECRET=true
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN useradd --system --uid 10001 racesafe
USER racesafe
EXPOSE 8000
CMD ["sh", "-c", "python -m alembic upgrade head && exec python -m uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000} --timeout-graceful-shutdown 10"]
