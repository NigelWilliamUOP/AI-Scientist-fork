# Deployment build is supplied, not verified in this sandbox (Docker absent).
FROM node:22-bookworm-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/tsconfig.json ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend APP_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 appuser && mkdir /data && chown appuser:appuser /data
COPY backend/osint ./backend/osint
COPY backend/osint_core ./backend/osint_core
COPY seeds ./seeds
COPY frontend/public/index.html frontend/public/styles.css ./frontend/public/
COPY --from=ui /ui/public/app.js ./frontend/public/app.js
USER appuser
EXPOSE 8000
# One process owns the SQLite job worker. Put this behind a TLS reverse proxy.
CMD ["sh","-c","exec uvicorn osint.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --no-access-log --no-proxy-headers"]
