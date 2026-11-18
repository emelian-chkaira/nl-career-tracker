#!/bin/sh
# Deploy the latest code:  sh deploy/update.sh
set -e
cd "$(dirname "$0")/.."
git pull --ff-only
docker compose -f docker-compose.prod.yml up -d --build
docker image prune -f >/dev/null
docker compose -f docker-compose.prod.yml ps
