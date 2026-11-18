# Contributing

- Backend: `cd backend && python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest`
- Run: `backend/run.sh` → http://localhost:8787
- Adding an ATS: write an adapter in `backend/careers/discovery.py` returning `list[dict(title, location, url, description, posted_at)]` or `None`, register it in `ADAPTERS` and `ATS_PATTERNS`, and add a fixture-based test.
- Adding companies: edit `backend/careers/clusters.py` (`Name|domain`).
- Keep crawling polite; never add scrapers for sites that forbid it (LinkedIn, Indeed, …).
- Tests must not touch a real database (`tests/conftest.py` uses a temp dir).
