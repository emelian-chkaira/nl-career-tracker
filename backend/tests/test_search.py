import pytest
from app.models import Company, Job
from app.services import ingest_service as ing, search_service as ss


@pytest.fixture()
def seeded(db):
    a = ing.add_company(db, "Acme Mobile BV"); b = ing.add_company(db, "Globex Data"); db.flush()
    J = lambda t, loc, d="", **k: dict(title=t, location=loc, url=f"https://x.nl/{abs(hash(t))}", description=d, posted_at=None, **k)
    ing.store_jobs(db, a, [J("Flutter Developer", "Eindhoven, Netherlands", "Build apps with Flutter and Dart. Remote friendly."),
                           J("Android Engineer", "Amsterdam, Netherlands", "Kotlin and Jetpack Compose mobile apps"),
                           J("iOS Developer", "Utrecht, Netherlands", "Swift and SwiftUI. Java is a plus."),
                           J("Flutter Intern", "Eindhoven, Netherlands", "Internship building Flutter apps", kind="internship")])
    ing.store_jobs(db, b, [J("Data Engineer", "Rotterdam, Netherlands", "Python, Spark, Airflow and SQL pipelines"),
                           J("Senior Java Backend Engineer", "Amsterdam, Netherlands", "Java Spring microservices"),
                           J("Accountant", "Utrecht, Netherlands", "Bookkeeping and tax")])
    db.commit(); return db


def titles(db, **kw):
    r = ss.run(db, ss.SearchParams(**{"mode": "keyword", "category": None, **kw}))
    return [db.get(Job, i).title for i in r["ids"]]


def test_synonyms_flutter_finds_mobile_roles(seeded):
    t = titles(seeded, q="flutter")
    assert "Flutter Developer" in t and "Android Engineer" in t and "iOS Developer" in t and "Accountant" not in t
    assert t.index("Flutter Developer") < t.index("Android Engineer")                  # direct matches rank first


def test_phrase_exclusion_and_fields(seeded):
    assert titles(seeded, q='"data engineer"') == ["Data Engineer"]
    assert "Senior Java Backend Engineer" not in titles(seeded, q="engineer -java")
    assert titles(seeded, q="title:accountant") == ["Accountant"]
    assert set(titles(seeded, q="company:globex")) == {"Data Engineer", "Senior Java Backend Engineer", "Accountant"}
    assert titles(seeded, q="location:rotterdam") == ["Data Engineer"]
    assert "Data Engineer" in titles(seeded, q="skill:airflow")


def test_typo_tolerance(seeded):
    assert "Flutter Developer" in titles(seeded, q="fluter")


def test_filters(seeded):
    assert all("Intern" in t for t in titles(seeded, kind="internship"))
    assert set(titles(seeded, city=["Amsterdam"])) == {"Android Engineer", "Senior Java Backend Engineer"}
    assert titles(seeded, skills=["spark"]) == ["Data Engineer"]
    assert set(titles(seeded, skills=["java", "spring"], skills_mode="all")) == {"Senior Java Backend Engineer"}
    assert all(t != "Accountant" for t in titles(seeded, category="tech"))


def test_default_sort_newest_without_query(seeded):
    assert len(titles(seeded)) >= 6


def test_facets(seeded):
    ids = ss.run(seeded, ss.SearchParams(category=None))["ids"]
    f = ss.facets(seeded, ids)
    assert any(c["value"] == "Amsterdam" for c in f["city"]) and any(s["value"] == "flutter" for s in f["skills"])


def test_http_search_and_suggest(client, seeded):
    r = client.get("/api/v1/jobs", params={"q": "flutter", "mode": "keyword", "category": ""})
    d = r.json(); assert r.status_code == 200 and d["total"] >= 3 and d["items"][0]["relevance"] is not None and "<mark>" in (d["items"][0]["snippet"] or "")
    assert "flutter" in client.get("/api/v1/jobs/suggest", params={"q": "flu"}).json()["skills"]
    assert client.get("/api/v1/jobs", params={"limit": 500}).status_code == 422


def test_semantic_mode_finds_by_meaning(seeded):
    from app.workers import embeddings
    if not embeddings.emb.available(): pytest.skip("embedding model unavailable")
    embeddings.backfill()
    r = ss.run(seeded, ss.SearchParams(q="smartphone application programmer", mode="semantic", category=None))
    t = [seeded.get(Job, i).title for i in r["ids"]]
    assert t and t[0] in ("Flutter Developer", "Android Engineer", "iOS Developer", "Flutter Intern") and "Accountant" not in t[:3]
