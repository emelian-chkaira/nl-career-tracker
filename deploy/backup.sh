#!/bin/sh
# Database backup to ./backups (keeps 14).  Cron example:  0 3 * * * sh /home/ubuntu/nl-career-tracker/deploy/backup.sh
set -e
cd "$(dirname "$0")/.."
mkdir -p backups
docker compose -f docker-compose.prod.yml exec -T db pg_dump -U careers careers | gzip > "backups/careers-$(date +%F).sql.gz"
ls -1t backups/careers-*.sql.gz | tail -n +15 | xargs -r rm --
