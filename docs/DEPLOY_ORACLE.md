# Deploying to Oracle Cloud (Always Free)

Result: `https://<your-domain>` serving the web app and API from one VM (Caddy for HTTPS -> API -> Postgres, plus the crawler worker).
Free tiers change; confirm the current *Always Free* limits on Oracle's pricing page before you start.

## 1. Oracle account
1. https://www.oracle.com/cloud/free/ -> sign up (a card is needed for identity verification).
2. Pick the **home region** carefully, it cannot be changed and Always Free resources only live there. **Netherlands Northwest (Amsterdam)** is the natural choice.

## 2. Create the server
**Compute -> Instances -> Create instance**
- Image: **Ubuntu 24.04** (the aarch64/Arm build).
- Shape: **VM.Standard.A1.Flex** (Ampere Arm), as much of the free allowance as available (at least 2 OCPU / 8 GB is comfortable; the small x86 "Micro" shape has 1 GB RAM and is too small).
- Networking: create/choose a public subnet and **assign a public IPv4**.
- Add your **SSH public key** (or let Oracle generate one and download it).
- Boot volume: 50 GB is plenty.
- "Out of host capacity" is common for A1: retry later, try another availability domain, or lower the OCPU/RAM.

## 3. Open ports 80 and 443 in Oracle's network
**Networking -> Virtual cloud networks -> your VCN -> Subnet -> Security list -> Add ingress rules**:
source `0.0.0.0/0`, protocol TCP, destination port `80`; and again for `443`. (Leave SSH 22 as is.)
Optional: **Networking -> Reserved public IPs** so the address never changes.

## 4. A free domain
1. https://www.duckdns.org -> sign in -> create a subdomain, e.g. `nlcareers` -> set its IP to the VM's public IP. You get `nlcareers.duckdns.org`.
2. (Later you can buy a real domain and point an A record at the same IP.)

## 5. Prepare the server
```bash
ssh ubuntu@<public-ip>
git clone https://github.com/emelian-chkaira/nl-career-tracker.git     # private repo: use a deploy key or a personal access token
cd nl-career-tracker
sh deploy/oracle-setup.sh        # Docker, firewall rules for 80/443, 4 GB swap
exit                             # log in again so the docker group applies
```

## 6. Configure and start
```bash
ssh ubuntu@<public-ip>
cd nl-career-tracker
cp deploy/env.production.example .env
nano .env                        # DOMAIN, POSTGRES_PASSWORD, CAREERS_JWT_SECRET (openssl rand -hex 32), admin e-mail, Firebase keys
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml logs -f api       # wait for "Application startup complete", Ctrl+C
```
The first build takes several minutes (Chromium and the embedding model). Caddy fetches the HTTPS certificate on first request
(needs DNS to point at the VM and ports 80/443 open).

## 7. First run
1. Open `https://<your-domain>`, sign up with the e-mail from `CAREERS_ADMIN_EMAILS` -> the **Crawler** page (with user management) appears.
2. Run the tasks *sponsors*, *discover*, *scan_all* (the worker does the crawling in the background).
3. Firebase: add the domain under *Authorized domains* and the OAuth web client's JavaScript origins, set the e-mail template action URL to `https://<domain>/action` (see [FIREBASE.md](FIREBASE.md)).
4. Mobile: build the app with `--dart-define=API_URL=https://<your-domain>`.

## 8. Operating it
| Task | Command |
|---|---|
| Deploy new code | `sh deploy/update.sh` |
| Logs | `docker compose -f docker-compose.prod.yml logs -f api worker` |
| Status | `docker compose -f docker-compose.prod.yml ps` |
| Backup | `sh deploy/backup.sh` (cron: `0 3 * * * sh ~/nl-career-tracker/deploy/backup.sh`) |
| Restore | `gunzip -c backups/careers-DATE.sql.gz \| docker compose -f docker-compose.prod.yml exec -T db psql -U careers careers` |

Copy `backups/` off the VM now and then (the disk is not a backup). Keep the VM patched: `sudo apt update && sudo apt -y upgrade`.

## Troubleshooting
- **HTTPS not issued**: DNS not pointing at the VM yet, or port 80/443 closed in the security list *or* in `iptables` (`sudo iptables -L INPUT -n --line-numbers`).
- **API restarts**: `logs api`; usually a missing `.env` value (`CAREERS_JWT_SECRET` is required in production).
- **Out of memory during build**: confirm swap (`free -h`) or build with fewer parallel steps; raise the VM's RAM share.
- **Oracle may reclaim idle Always Free instances**: check their current policy; the crawler worker keeps the machine busy.
- **CV -> PDF**: the image has no local LaTeX compiler; the CV Studio uses the opt-in public converter instead.
