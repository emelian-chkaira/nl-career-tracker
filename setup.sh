#!/usr/bin/env bash
# One-click setup for NL Career Tracker.  Run:  ./setup.sh
#
#   ./setup.sh               everything, then start the app on http://localhost:8787
#   ./setup.sh --docker      run the whole stack in Docker (no Python or Node needed)
#   ./setup.sh --no-start    prepare everything but do not start the servers
#   ./setup.sh --no-browser  skip the Chromium download (JS-rendered career pages will not be crawled)
#
# What it does: creates .env with a random secret, starts Postgres (pgvector) in Docker, installs the backend and the web app,
# creates the tables, loads the ready-made starter data (3,000+ Dutch tech companies, a snapshot of open jobs, the IND sponsor list)
# and starts the API, the crawler worker and the website. Safe to run again: nothing is overwritten.
set -euo pipefail
cd "$(dirname "$0")"

DOCKER_MODE=0; START=1; BROWSER=1
for a in "$@"; do case "$a" in --docker) DOCKER_MODE=1;; --no-start) START=0;; --no-browser) BROWSER=0;; -h|--help) sed -n 2,13p "$0"; exit 0;; *) echo "unknown option: $a"; exit 2;; esac; done

say()  { printf "\n\033[1;36m▸ %s\033[0m\n" "$*"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$*"; }
die()  { printf "\n\033[31m✗ %s\033[0m\n" "$*" >&2; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

say "Checking your machine"
have docker || die "Docker is required (it runs the database). Install Docker Desktop or Docker Engine, then run ./setup.sh again."
docker info >/dev/null 2>&1 || die "Docker is installed but not running. Start Docker, then run ./setup.sh again."
ok "Docker is running"

PY=""; for c in python3.13 python3.12 python3.11 python3; do
  if have "$c" && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then PY="$c"; break; fi; done
NODE_OK=0; if have node && node -e 'process.exit(+process.versions.node.split(".")[0] >= 18 ? 0 : 1)' 2>/dev/null; then NODE_OK=1; fi
if [ "$DOCKER_MODE" = 0 ] && { [ -z "$PY" ] || [ "$NODE_OK" = 0 ]; }; then
  echo "  Python 3.11+ and Node 18+ were not both found, so the app will run in Docker instead."; DOCKER_MODE=1
fi

say "Creating .env"
if [ ! -f .env ]; then
  cp .env.example .env
  SECRET="$( (openssl rand -hex 32 2>/dev/null) || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  if grep -q '^CAREERS_JWT_SECRET=' .env; then sed -i.bak "s|^CAREERS_JWT_SECRET=.*|CAREERS_JWT_SECRET=${SECRET}|" .env && rm -f .env.bak; else echo "CAREERS_JWT_SECRET=${SECRET}" >> .env; fi
  ok "wrote .env with a fresh random secret"
else ok ".env already exists, keeping it"; fi

if [ "$DOCKER_MODE" = 1 ]; then
  say "Building and starting everything in Docker (the first build takes a few minutes)"
  docker compose up -d --build
  say "Waiting for the website"
  for i in $(seq 1 90); do curl -fs http://localhost:8787/healthz >/dev/null 2>&1 && break; sleep 2; done
  curl -fs http://localhost:8787/healthz >/dev/null 2>&1 || die "The API did not come up. See: docker compose logs api"
  printf "\n\033[1;32m✓ Ready: http://localhost:8787\033[0m\n  Register an account: the first one becomes the admin.\n  Stop: docker compose down   ·   Logs: docker compose logs -f\n"
  exit 0
fi

say "Starting the database"
docker compose up -d db
for i in $(seq 1 40); do [ "$(docker inspect -f '{{.State.Health.Status}}' "$(docker compose ps -q db)" 2>/dev/null)" = healthy ] && break; sleep 2; done
ok "Postgres with pgvector is up"

say "Installing the backend ($PY)"
if [ ! -d backend/.venv ]; then "$PY" -m venv backend/.venv; fi
backend/.venv/bin/pip install -q --upgrade pip
backend/.venv/bin/pip install -q -r backend/requirements.txt
ok "dependencies installed"
if [ "$BROWSER" = 1 ]; then
  say "Downloading Chromium for JavaScript career pages (about 150 MB, one time)"
  backend/.venv/bin/playwright install chromium >/dev/null 2>&1 && ok "Chromium ready" || echo "  could not install Chromium; re-run later with: backend/.venv/bin/playwright install chromium"
fi

say "Creating tables and loading the ready-made data"
( cd backend && set -a && . ../.env && set +a && .venv/bin/alembic upgrade head >/dev/null && PYTHONPATH=. .venv/bin/python -m app.cli seed && PYTHONPATH=. .venv/bin/python -m app.cli stats | head -4 )

say "Building the website"
( cd frontend && { [ -d node_modules ] || npm ci --silent; } && npm run build --silent )
ok "website built"

if [ "$START" = 0 ]; then printf "\n\033[1;32m✓ Set up.\033[0m Start it with: ./backend/run.sh api   (and, in another terminal, ./backend/run.sh worker)\n"; exit 0; fi

say "Starting the crawler worker in the background and the app in front"
mkdir -p backend/data; ( nohup ./backend/run.sh worker > backend/data/worker.log 2>&1 & )
printf "\n\033[1;32m✓ Ready: http://localhost:8787\033[0m\n  Register an account: the first one becomes the admin.\n  The crawler is refreshing jobs in the background (log: backend/data/worker.log). Press Ctrl+C to stop the app.\n\n"
exec ./backend/run.sh api
