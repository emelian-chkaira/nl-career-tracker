"""Find companies by the job boards they use.

Certificate-transparency logs (crt.sh) list every `<company>.recruitee.com`-style hostname that ever got a certificate, which gives us thousands of
small and medium employers that no company directory lists. Each slug is then probed through the public ATS API; the worker keeps only companies
that really have NL tech postings.  Public data only; polite per-host rate limits come from discovery.get()."""
import json, re, subprocess, time

DOMAINS = {  # ats adapter name -> hostname suffix that carries the company slug as a subdomain
    "recruitee": ["recruitee.com"], "teamtailor": ["teamtailor.com"], "personio": ["jobs.personio.de", "jobs.personio.com"],
    "bamboohr": ["bamboohr.com"], "homerun": ["homerun.co"],
}
SKIP = {"www", "api", "app", "help", "blog", "careers", "jobs", "mail", "support", "status", "docs", "dev", "staging", "test", "demo", "admin", "cdn", "static", "assets", "login", "partners", "info", "get"}


def crt_slugs(domain: str, retries=3) -> set[str]:
    import os
    from app.core.config import settings
    cache = os.path.join(settings.data_dir, "ct", domain + ".json")
    rows = None
    if os.path.exists(cache) and time.time() - os.path.getmtime(cache) < 7 * 86400:
        try: rows = json.load(open(cache))
        except Exception: rows = None
    for i in range(0 if rows else retries):
        try:
            raw = subprocess.run(["curl", "-s", "-m", "200", f"https://crt.sh/?q=%25.{domain}&output=json"], capture_output=True, text=True, timeout=210).stdout
            rows = json.loads(raw); os.makedirs(os.path.dirname(cache), exist_ok=True); open(cache, 'w').write(raw); break
        except Exception: rows = None; time.sleep(10 * (i + 1))
    if not rows: return set()
    out = set()
    for r in rows:
        for n in r.get("name_value", "").split("\n"):
            n = n.lower().strip()
            if n.endswith("." + domain) and not n.startswith("*"):
                s = n[: -len(domain) - 1]
                if "." not in s and s not in SKIP and re.fullmatch(r"[a-z0-9][a-z0-9-]{1,60}", s) and not s.startswith(("s-", "jobs-widget")): out.add(s)
    return out


def pretty(slug: str) -> str:
    return " ".join(w.capitalize() if len(w) > 3 else w.upper() if len(w) <= 2 else w.capitalize() for w in slug.replace("_", "-").split("-") if w)
