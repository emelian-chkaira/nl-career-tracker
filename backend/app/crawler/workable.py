"""Workable public job search (Netherlands) — used only to DISCOVER companies; jobs are then read from each company's own board."""
from .discovery import get, _txt
from .nl import NL_RE

QUERIES = ["developer", "software engineer", "engineer", "data", "devops", "frontend", "backend", "full stack", "mobile", "ios", "android", "flutter", "python", "java", "react", "cloud", "security", "qa", "machine learning", "ai", "product manager", "ux designer", "it support", "embedded", "intern", "internship", "stage", "graduate", "trainee", "werkstudent", "analyst", "architect", "sre", "platform", "sap", "network", "scrum", "technical"]

def workable_nl():
    """Workable's public job search, filtered to the Netherlands, over many tech queries with pagination."""
    out, seen = [], set()
    for q in QUERIES:
        tok = None
        for _ in range(15):
            d = get(f"https://jobs.workable.com/api/v1/jobs?query={q.replace(' ', '+')}&location=Netherlands" + (f"&pageToken={tok}" if tok else ""), True, False)
            if not d or not d.get("jobs"): break
            for j in d["jobs"]:
                if j["id"] in seen: continue
                loc = j.get("location") or {}
                city = ", ".join(x for x in [loc.get("city"), loc.get("countryName")] if x)
                if not NL_RE.search(city): continue
                seen.add(j["id"])
                out.append(dict(company=(j.get("company") or {}).get("title", "Unknown"), website=(j.get("company") or {}).get("website"), title=j["title"], location=city, url=j["url"],
                                description=_txt((j.get("description") or "") + (j.get("requirementsSection") or "") + (j.get("benefitsSection") or "")), posted_at=j.get("created")))
            tok = d.get("nextPageToken")
            if not tok: break
    return out
