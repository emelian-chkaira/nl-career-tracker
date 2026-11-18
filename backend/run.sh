#!/bin/sh
# Dev launcher: `./run.sh api` (http://localhost:8787, serves ../frontend/dist) or `./run.sh worker` (crawler, alerts, embeddings).
cd "$(dirname "$0")" || exit 1
[ -f ../.env ] && set -a && . ../.env && set +a
[ -f .env.local ] && set -a && . ./.env.local && set +a
case "$1" in
  worker) exec .venv/bin/python -m app.workers.run ;;
  migrate) exec .venv/bin/alembic upgrade head ;;
  *) .venv/bin/alembic upgrade head && exec .venv/bin/uvicorn app.main:app --host "${HOST:-0.0.0.0}" --port "${PORT:-8787}" ;;
esac
