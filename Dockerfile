# --- web build
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build

# --- API + worker image (the API serves the built web app from /app/frontend/dist)
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/ms-playwright CAREERS_DATA_DIR=/data
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir -r backend/requirements.txt \
 && playwright install --with-deps chromium \
 && useradd -m app && mkdir -p /data && chown app /data
COPY backend backend
COPY --from=web /web/dist frontend/dist
USER app
WORKDIR /app/backend
EXPOSE 8787
VOLUME /data
HEALTHCHECK CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8787/healthz')" || exit 1
CMD ["sh","-c","alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8787 --proxy-headers"]
