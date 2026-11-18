from app.crawler import discovery as d

def test_detect_more_ats_vendors():
    assert d.detect_ats('<a href="https://acme.carerix.net/x">') == ("carerix", "acme")
    assert d.detect_ats('<iframe src="https://join.com/companies/acme-bv">') == ("join", "acme-bv")
    assert d.detect_ats('<a href="https://boards.greenhouse.io/foo">') == ("greenhouse", "foo")

def test_slug_guesses_skip_short_first_word():
    assert "the" not in d.slugs("The Hague Tech")
    assert d.slugs("Adyen N.V.")[0] == "adyen"

def test_find_careers_uses_footer_link_then_sitemap(monkeypatch):
    pages = {"https://x.nl/sitemap.xml": "<urlset><url><loc>https://x.nl/over-ons/werken-bij-x</loc></url></urlset>",
             "https://x.nl/over-ons/werken-bij-x": "<html>vacatures</html>"}
    monkeypatch.setattr(d, "get", lambda u, *a, **k: pages.get(u))
    link, html = d.find_careers("https://x.nl", "<html><body>no links</body></html>")
    assert link == "https://x.nl/over-ons/werken-bij-x"

def test_empty_board_is_ignored(monkeypatch):
    monkeypatch.setattr(d, "ADAPTERS", {"greenhouse": lambda s: [], "lever": lambda s: [dict(title="t", url="u", location="", description="", posted_at=None)]})
    assert d.find_board("Acme")[0] == "lever"

def test_student_pages_found_from_links(monkeypatch):
    html = '<a href="/en/students-graduates">Students</a><a href="/about">About</a><a href="https://other.com/internships">x</a>'
    urls = d.student_pages("https://acme.nl", html)
    assert "https://acme.nl/en/students-graduates" in urls and all("other.com" not in u for u in urls)

def test_student_page_jobs_tagged_internship(monkeypatch):
    pages = {"https://acme.nl/internships": '<a href="/job/123456-software-dev">Software Development Project</a><a href="/job/123457-data">Data Analysis Project</a><a href="/job/123458-ops">Operations Support</a><a href="/job/123459-x">Research Assistant Role</a><a href="/job/123450-y">Hardware Design Role</a>'}
    monkeypatch.setattr(d, "get", lambda u, *a, **k: pages.get(u))
    jobs = d.scan_student_pages("https://acme.nl", "", "", set())
    assert jobs and all(j["kind"] == "internship" for j in jobs)
