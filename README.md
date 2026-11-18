# NL Career Tracker

Open-source job & internship search for the Netherlands that reads **employers' own career pages** (no aggregators). One API, a React web app and a Flutter app.
Inspired by [career-ops](https://github.com/career-ops-hq/career-ops). IND recognised sponsors are only a **badge**, never a filter.

## What it does
- **Search** on Postgres: full-text (`tsvector`, ranked, highlighted snippets), **semantic** (pgvector + a local embedding model), and **hybrid** (reciprocal-rank fusion). Advanced syntax: `"exact phrase"`, `-exclude`, `title:` `company:` `location:` `skill:`; typo tolerance (pg_trgm); ontology synonyms ("flutter" also finds Android/iOS roles); facets (city, type, language, skills, companies); filters for remote, sponsor flag, salary, date; sorts: best match, newest, salary, **my fit**.
- **Accounts**: register/login (argon2id, short-lived JWT access tokens, rotating refresh tokens with reuse detection, httpOnly cookie for web, body token for mobile), profile (skills/titles/cities), per-user pipeline and notes.
- **Job alerts**: save any search, choose instant/daily/weekly; the worker finds new matches, creates in-app notifications and e-mails (SMTP optional; without it e-mails are recorded as "skipped").
- **Market dashboard**: open roles, hiring companies, new postings per day, top cities/companies, contract types, skills demand with 30-day trend, salary stats.
- **CV & cover letters**: import PDF/DOCX/text/LaTeX, PDF -> LaTeX conversion, tailor the LaTeX in place to a job, compile with tectonic, cover-letter drafts. Stateless (nothing stored server-side). Optional opt-in LLM polish with `ANTHROPIC_API_KEY`.
- **Crawler**: ATS APIs -> career-page crawl (+ sitemap) -> JSON-LD -> headless browser; NL-only, deduplicated; student/internship pages are crawled and classified.

## Architecture
```
backend/  FastAPI + SQLAlchemy 2 + Alembic + Postgres 16 (pgvector, pg_trgm)
  app/core        config (CAREERS_* env), db, security, deps, rate limit
  app/models      ORM tables            app/schemas   request/response models
  app/services    business logic (auth, search, jobs, analytics, alerts, ingest, embeddings, task queue)
  app/api/v1      thin routers: auth, jobs, companies, me, analytics, cv, admin, tasks
  app/crawler     discovery & ATS adapters      app/cvtools   CV / LaTeX tools
  app/workers     separate process: DB-backed task queue (FOR UPDATE SKIP LOCKED) + scheduler (alerts, embeddings, refresh)
  migrations/     Alembic          tests/   pytest against a real Postgres
frontend/ React 18 + TypeScript + Vite, feature folders (auth, jobs, companies, dashboard, alerts, pipeline, cv, profile, admin), TanStack Query, Recharts
(the Flutter app lives in its own repo: `nl-career-tracker-mobile`, which talks to this API via `--dart-define=API_URL=...`)
```
The web and API workers scale horizontally (stateless API; tasks coordinate through Postgres). The in-process rate limiter is per instance; put a gateway/Redis limiter in front when running several API replicas.

## Quick start (local)
```bash
docker compose up -d db                       # Postgres + pgvector on localhost:5433
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/playwright install chromium         # JS-rendered career pages
cp ../.env.example ../.env                    # set CAREERS_JWT_SECRET, CAREERS_ADMIN_EMAILS
./run.sh api                                  # migrates, then http://localhost:8787 (API docs: /api/docs)
./run.sh worker                               # in a second terminal: crawling, alerts, embeddings
cd ../frontend && npm install && npm run dev  # http://localhost:5173 (proxies /api to :8787)
cd ../nl-career-tracker-mobile && flutter run --dart-define=API_URL=http://localhost:8787
```
Register with an e-mail listed in `CAREERS_ADMIN_EMAILS` to get the **Admin** page, then run *scan_all*, *discover*, *logos*, *sponsors*. For production build the web app (`npm run build`); the API serves `frontend/dist`.
Import data from the previous SQLite version with `python -m scripts.migrate_sqlite <careers.db> --truncate`.

Tests: `cd backend && python -m pytest -q` (needs the Postgres from `docker compose up -d db`).

## Hosting it publicly
```bash
cp .env.example .env     # set DATABASE_URL, CAREERS_JWT_SECRET=$(openssl rand -hex 32), CAREERS_ADMIN_EMAILS, CAREERS_COOKIE_SECURE=1, CAREERS_TRUST_PROXY=1, CAREERS_CONTACT
docker compose up -d --build     # db + api (runs migrations) + worker
```
Put it behind HTTPS (Caddy/nginx/Traefik). Set `CAREERS_ALLOW_REGISTRATION=0` for a private instance. Anonymous visitors can search and use the CV tools (rate limited); crawl/admin endpoints need the admin role. Read [DATA_SOURCES.md](DATA_SOURCES.md) first (licences, attribution, crawler etiquette) and set `CAREERS_CONTACT` so site owners can reach you.

## Configuration
Everything is an environment variable: see [.env.example](.env.example) and `backend/app/core/config.py`.

## How a company is scanned (`backend/app/crawler/discovery.py`)
1. Known ATS board, else slug-guess the public APIs (Greenhouse, Lever, Ashby, Recruitee, SmartRecruiters, Workable, Teamtailor, Personio, BambooHR, Homerun, Workday). Empty boards are ignored (often another company with the same slug).
2. Resolve the website, find the careers page (nav/footer links → common paths → `werkenbij.`/`careers.` subdomains → sitemap), detect more ATS vendors from it.
3. schema.org `JobPosting` JSON-LD → generic job links → headless Chromium (XHR interception, pagination, "load more").
4. Duplicates (same title/location under different URLs) are merged; vanished postings are marked `expired`; dead-end companies back off exponentially.

## Tests / CI
`cd backend && .venv/bin/pytest` (temp database, never touches your data). GitHub Actions runs backend tests and `flutter analyze`.

## Limits
- Slug/domain guesses can match the wrong company; some career pages need logins/clicks or block bots.
- Only the Netherlands is implemented (`nl.py`); other countries need a matcher.
- Search is keyword/ontology based (no embeddings yet); FTS5 + semantic ranking are planned.
- Salary thresholds are 2026 IND values and need updating each January. Sponsor flags are informational, not legal advice.
- Never scrapes LinkedIn/Indeed/Glassdoor/search results.

License: MIT.
