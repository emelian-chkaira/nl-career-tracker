"""Market dashboard: aggregates over open jobs (all SQL, cacheable)."""
from sqlalchemy import text
from sqlalchemy.orm import Session


def _rows(db, sql, **a): return [dict(r._mapping) for r in db.execute(text(sql), a)]
_TECH = "j.category = 'tech'"


def overview(db: Session, days: int = 90, category: str = "tech", kind: str | None = None) -> dict:
    where = "j.status='open'" + (f" AND j.category=:cat" if category else "") + (" AND j.job_type IN ('internship','traineeship')" if kind == "internship" else (" AND j.job_type NOT IN ('internship','traineeship')" if kind == "job" else ""))
    a = {"cat": category, "days": days}
    kpi = _rows(db, f"""SELECT count(*) open_jobs, count(DISTINCT company_id) hiring_companies,
        count(*) FILTER (WHERE j.job_type IN ('internship','traineeship')) internships,
        count(*) FILTER (WHERE COALESCE(j.posted_at, j.first_seen::date) >= current_date - 7) new_7d,
        count(*) FILTER (WHERE COALESCE(j.posted_at, j.first_seen::date) >= current_date - 14 AND COALESCE(j.posted_at, j.first_seen::date) < current_date - 7) prev_7d,
        count(*) FILTER (WHERE j.remote) remote_jobs,
        count(*) FILTER (WHERE j.language='english_ok') english_ok,
        count(*) FILTER (WHERE j.salary_min IS NOT NULL) with_salary
        FROM jobs j WHERE {where}""", **a)[0]
    kpi["sponsor_jobs"] = _rows(db, f"SELECT count(*) n FROM jobs j JOIN companies c ON c.id=j.company_id WHERE {where} AND c.sponsor_status IN ('recognised','possible')", **a)[0]["n"]
    daily = _rows(db, f"""SELECT d::date AS day, coalesce(n, 0) AS new_jobs FROM generate_series(current_date - make_interval(days => :days), current_date, '1 day') d
        LEFT JOIN (SELECT COALESCE(j.posted_at, j.first_seen::date) AS day, count(*) n FROM jobs j WHERE {where} GROUP BY 1) x ON x.day = d::date ORDER BY d""", **a)
    cities = _rows(db, f"SELECT j.city AS name, count(*) AS jobs FROM jobs j WHERE {where} AND j.city IS NOT NULL GROUP BY j.city ORDER BY jobs DESC LIMIT 15", **a)
    by_type = _rows(db, f"SELECT j.job_type AS name, count(*) AS jobs FROM jobs j WHERE {where} GROUP BY j.job_type ORDER BY jobs DESC", **a)
    lang = _rows(db, f"SELECT j.language AS name, count(*) AS jobs FROM jobs j WHERE {where} GROUP BY j.language ORDER BY jobs DESC", **a)
    companies = _rows(db, f"SELECT c.id, c.name, c.logo, c.sponsor_status, count(*) AS jobs FROM jobs j JOIN companies c ON c.id=j.company_id WHERE {where} GROUP BY c.id ORDER BY jobs DESC LIMIT 12", **a)
    skills = _rows(db, f"""SELECT s.skill AS name, count(*) AS jobs,
        count(*) FILTER (WHERE COALESCE(j.posted_at, j.first_seen::date) >= current_date - 30) AS last_30d,
        count(*) FILTER (WHERE COALESCE(j.posted_at, j.first_seen::date) >= current_date - 60 AND COALESCE(j.posted_at, j.first_seen::date) < current_date - 30) AS prev_30d
        FROM job_skills s JOIN jobs j ON j.id=s.job_id WHERE {where} GROUP BY s.skill ORDER BY jobs DESC LIMIT 25""", **a)
    for s in skills: s["trend"] = (s["last_30d"] - s["prev_30d"]) / s["prev_30d"] if s["prev_30d"] else None
    salary = _rows(db, f"""SELECT j.job_type AS name, count(*) n, round(avg(m)::numeric) avg, round(percentile_cont(0.5) WITHIN GROUP (ORDER BY m)::numeric) median
        FROM (SELECT j.job_type, (CASE WHEN j.salary_period='year' THEN j.salary_min/12 ELSE j.salary_min END) m FROM jobs j WHERE {where} AND j.salary_min IS NOT NULL) j GROUP BY j.job_type""", **a)
    return {"kpi": kpi, "daily": daily, "cities": cities, "types": by_type, "languages": lang, "companies": companies, "skills": skills, "salary": salary}
