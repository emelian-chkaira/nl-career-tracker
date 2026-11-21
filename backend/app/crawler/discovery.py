"""Company web-resolution: name -> website -> careers page -> ATS -> postings.
Order (career-ops style): ATS public APIs by slug guess, then website + careers-page crawl, JSON-LD, generic links.
Polite: robots.txt honoured, 1 req/sec/host, UA names the project. Never scrapes LinkedIn/Indeed/Glassdoor or search-engine result pages."""
import re, json, time, os, urllib.robotparser, threading
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup
from .text import norm

from app.core.config import settings
UA, LOGO_DIR, BRAVE_API_KEY, BROWSER_SLOTS = settings.user_agent, os.path.join(settings.data_dir, "logos"), settings.brave_api_key, settings.browser_slots
_last: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
_lk = threading.Lock()
client = httpx.Client(headers={"User-Agent": UA, "Accept-Language": "en,nl"}, follow_redirects=True, timeout=15)

FAST_HOSTS = ("greenhouse.io", "lever.co", "ashbyhq.com", "recruitee.com", "smartrecruiters.com", "workable.com", "personio", "bamboohr.com", "myworkdayjobs.com", "homerun.co", "teamtailor.com")
def _wait(host):
    gap = 0.2 if host.endswith(FAST_HOSTS) else 1.0
    with _lk:
        d = gap - (time.time() - _last.get(host, 0))
        _last[host] = time.time() + max(d, 0)
    if d > 0: time.sleep(d)

def allowed(url):
    p = urlparse(url); base = f"{p.scheme}://{p.netloc}"
    if base not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            r = client.get(base + "/robots.txt")
            rp.parse(r.text.splitlines()) if r.status_code == 200 else rp.parse([])
        except Exception:
            rp = None
        _robots[base] = rp
    rp = _robots[base]
    return True if rp is None else rp.can_fetch(UA, url)

def get(url, json_=False, check_robots=True):
    if check_robots and not allowed(url): return None
    _wait(urlparse(url).netloc)
    try:
        r = client.get(url)
        if r.status_code != 200: return None
        return r.json() if json_ else r.text
    except Exception:
        return None

def slugs(name):
    n = re.sub(r"\b(b\.?v\.?|n\.?v\.?|holding|group)\b", "", name.lower())
    words = re.findall(r"[a-z0-9]+", n)
    if not words: return []
    out = ["".join(words), "-".join(words)] + ([words[0]] if len(words[0]) > 4 else [])
    return list(dict.fromkeys(s for s in out if len(s) > 2))

def _txt(html):
    h = (html or "")
    if "&lt;" in h[:400]: h = __import__("html").unescape(h)
    soup = BeautifulSoup(h, "lxml")
    for br in soup.find_all(["br"]): br.replace_with("\n")
    for li in soup.find_all("li"): li.insert_before("• ")
    txt = soup.get_text("\n", strip=True)
    return re.sub(r"\n{3,}", "\n\n", txt)[:15000]

# ---- ATS adapters: each returns list of dicts or None when the board does not exist ----
def greenhouse(s):
    d = get(f"https://boards-api.greenhouse.io/v1/boards/{s}/jobs?content=true", True, False)
    if not d or "jobs" not in d: return None
    return [dict(title=j["title"], location=(j.get("location") or {}).get("name", ""), url=j["absolute_url"],
                 description=_txt(j.get("content", "")), posted_at=j.get("updated_at")) for j in d["jobs"]]
def lever(s):
    d = get(f"https://api.lever.co/v0/postings/{s}?mode=json", True, False)
    if not isinstance(d, list): return None
    return [dict(title=j["text"], location=(j.get("categories") or {}).get("location", ""), url=j["hostedUrl"],
                 description=(j.get("descriptionPlain") or "")[:15000], posted_at=j.get("createdAt")) for j in d]
def ashby(s):
    d = get(f"https://api.ashbyhq.com/posting-api/job-board/{s}", True, False)
    if not d or "jobs" not in d: return None
    return [dict(title=j["title"], location=j.get("location", ""), url=j["jobUrl"],
                 description=(j.get("descriptionPlain") or "")[:15000], posted_at=j.get("publishedAt")) for j in d["jobs"]]
def recruitee(s):
    d = get(f"https://{s}.recruitee.com/api/offers/", True, False)
    if not d or "offers" not in d: return None
    return [dict(title=j["title"], location=j.get("location", ""), url=j["careers_url"],
                 description=_txt(j.get("description")), posted_at=j.get("published_at")) for j in d["offers"]]
def smartrecruiters(s):
    d = get(f"https://api.smartrecruiters.com/v1/companies/{s}/postings?limit=100", True, False)
    if not d or not d.get("content"): return None
    return [dict(title=j["name"], location=", ".join(filter(None, [(j.get("location") or {}).get("city"), (j.get("location") or {}).get("country")])),
                 url=f"https://jobs.smartrecruiters.com/{s}/{j['id']}", description="", posted_at=j.get("releasedDate")) for j in d["content"]]
def workable(s):
    d = get(f"https://apply.workable.com/api/v1/widget/accounts/{s}", True, False)
    if not d or not d.get("jobs"): return None
    return [dict(title=j["title"], location=", ".join(filter(None, [j.get("city"), j.get("country")])), url=j["url"],
                 description=_txt(j.get("description")), posted_at=j.get("published_on")) for j in d["jobs"]]
def teamtailor(s):
    x = get(f"https://{s}.teamtailor.com/jobs.rss", False, False)
    if not x or "<item>" not in x: return None
    out = []
    for it in BeautifulSoup(x, "xml").find_all("item"):
        g = lambda t: (it.find(t).get_text(" ", strip=True) if it.find(t) else "")
        out.append(dict(title=g("title"), location=g("remoteStatus") and g("locations") or g("locations") or "", url=g("link"), description=_txt(g("description")), posted_at=g("pubDate")))
    return out
def personio(s):
    x = get(f"https://{s}.jobs.personio.de/xml", False, False) or get(f"https://{s}.jobs.personio.com/xml", False, False)
    if not x or "<position" not in x: return None
    out = []
    for p in BeautifulSoup(x, "xml").find_all("position"):
        g = lambda t: (p.find(t).get_text(" ", strip=True) if p.find(t) else "")
        out.append(dict(title=g("name"), location=g("office"), url=f"https://{s}.jobs.personio.de/job/{g('id')}", description=_txt(" ".join(v.get_text(" ") for v in p.find_all("value"))), posted_at=g("createdAt")))
    return out
def bamboohr(s):
    d = get(f"https://{s}.bamboohr.com/careers/list", True, False)
    if not d or not d.get("result"): return None
    return [dict(title=j["jobOpeningName"], location=", ".join(filter(None, [(j.get("location") or {}).get("city"), (j.get("location") or {}).get("state")])),
                 url=f"https://{s}.bamboohr.com/careers/{j['id']}", description="", posted_at=None) for j in d["result"]]
def homerun(s):
    d = get(f"https://feed.homerun.co/{s}", True, False)
    if not isinstance(d, dict) or not d.get("vacancies"): return None
    return [dict(title=j.get("title", ""), location=j.get("city", ""), url=j.get("url") or j.get("apply_url"), description=_txt(j.get("description")), posted_at=j.get("published_at")) for j in d["vacancies"]]
def workday(s):
    """slug = tenant|wdN|site"""
    try: tenant, wd, site = s.split("|")
    except ValueError: return None
    host = f"https://{tenant}.{wd}.myworkdayjobs.com"
    out = []
    for off in range(0, 200, 20):
        _wait(urlparse(host).netloc)
        try:
            r = client.post(f"{host}/wday/cxs/{tenant}/{site}/jobs", json={"limit": 20, "offset": off, "searchText": "", "appliedFacets": {}})
            if r.status_code != 200: break
            d = r.json()
        except Exception: break
        for j in d.get("jobPostings", []):
            out.append(dict(title=j["title"], location=j.get("locationsText", ""), url=f"{host}/en-US/{site}{j['externalPath']}", description="", posted_at=j.get("postedOn")))
        if len(d.get("jobPostings", [])) < 20: break
    return out or None
ADAPTERS = {"teamtailor": teamtailor, "personio": personio, "bamboohr": bamboohr, "homerun": homerun, "workday": workday, "greenhouse": greenhouse, "lever": lever, "ashby": ashby, "recruitee": recruitee,
            "smartrecruiters": smartrecruiters, "workable": workable}

def find_board(name, hint_slug=None):
    """Probe every ATS with slug guesses. -> (ats, slug, jobs) or None"""
    for s in ([hint_slug] if hint_slug else []) + slugs(name):
        for ats, fn in ADAPTERS.items():
            jobs = fn(s)
            if jobs: return ats, s, jobs        # empty boards are ignored: they are usually another company with the same slug
    return None

# ---- website + careers page ----
CAREER_WORDS = re.compile(r"career|jobs|vacanc|vacature|werken[- ]?bij|join[- ]?us|solliciteer|traineeship|stage", re.I)
ATS_PATTERNS = [("workday", r"([\w-]{1,80})\.(wd\d+)\.myworkdayjobs\.com/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]{1,80})"),
                ("teamtailor", r"([\w-]{1,80})\.teamtailor\.com"), ("personio", r"([\w-]{1,80})\.jobs\.personio\.(?:de|com)"),
                ("bamboohr", r"([\w-]{1,80})\.bamboohr\.com"), ("homerun", r"([\w-]{1,80})\.homerun\.co"),
                ("greenhouse", r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([\w-]{1,80})"),
                ("lever", r"jobs\.lever\.co/([\w-]{1,80})"), ("ashby", r"jobs\.ashbyhq\.com/([\w.-]{1,80})"),
                ("recruitee", r"([\w-]{1,80})\.recruitee\.com"), ("workable", r"apply\.workable\.com/([\w-]{1,80})"),
                ("smartrecruiters", r"(?:jobs|careers)\.smartrecruiters\.com/([\w-]{1,80})"),
                ("join", r"join\.com/companies/([\w-]{1,80})"), ("jobvite", r"jobs\.jobvite\.com/([\w-]{1,80})"), ("breezy", r"([\w-]{1,80})\.breezy\.hr"),
                ("carerix", r"([\w-]{1,80})\.carerix\.net"), ("otys", r"([\w-]{1,80})\.otys\.nl"), ("emply", r"([\w-]{1,80})\.emply\.com"), ("icims", r"([\w-]{1,80})\.icims\.com")]

def resolve_website(name):
    """Official search API (Brave, optional key) -> Wikidata -> guessed domains. Verified by fetching the homepage."""
    cands = []
    key = BRAVE_API_KEY
    if key:
        try:
            r = client.get("https://api.search.brave.com/res/v1/web/search", params={"q": f'"{name}" official website Netherlands', "count": 5},
                           headers={"X-Subscription-Token": key, "Accept": "application/json"})
            for it in r.json().get("web", {}).get("results", []):
                u = urlparse(it["url"]); cands.append((f"{u.scheme}://{u.netloc}", "search-api"))
        except Exception: pass
    if re.fullmatch(r"[\w-]+\.(com|nl|io|eu|ai|co)", name.strip().lower()):  # name already is a domain
        cands.insert(0, (f"https://www.{name.strip().lower()}", "name-is-domain")); cands.insert(1, (f"https://{name.strip().lower()}", "name-is-domain"))
    for s in ([] if cands and cands[0][1] == "name-is-domain" else slugs(name)[:2]):
        for tld in ("com", "nl"):
            cands.append((f"https://www.{s}.{tld}", "guess")); cands.append((f"https://{s}.{tld}", "guess"))
    key_words = set(norm(name).split())
    for base, via in cands:
        html = get(base, check_robots=False)
        if not html: continue
        title = (BeautifulSoup(html, "lxml").title.get_text(" ") if BeautifulSoup(html, "lxml").title else "").lower()
        # guessed domains must carry the company name in the <title> (avoids look-alike domains)
        if key_words and (any(w in title for w in key_words if len(w) > 2) or (via != "guess" and any(w in html.lower() for w in key_words if len(w) > 2))):
            return base, html, via
    return None

CAREER_PATHS = ("/careers", "/career", "/jobs", "/vacatures", "/vacature", "/werken-bij", "/werkenbij", "/join-us", "/about/careers", "/company/careers", "/en/careers", "/nl/careers", "/nl/vacatures", "/work-with-us")
def sitemap_career_urls(base):
    """Career-looking URLs from /sitemap.xml (one level of sitemap index)."""
    out = []
    for sm in (urljoin(base, "/sitemap.xml"), urljoin(base, "/sitemap_index.xml")):
        x = get(sm)
        if not x: continue
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", x)
        for l in locs[:6]:
            if l.endswith(".xml") and CAREER_WORDS.search(l):
                y = get(l)
                if y: locs += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", y)[:400]
        out += [l for l in locs if CAREER_WORDS.search(urlparse(l).path) and not l.endswith(".xml") and urlparse(l).path.count("/") <= 3]
        if out: break
    return out[:6]

def find_careers(base, home_html):
    soup = BeautifulSoup(home_html, "lxml")
    host = urlparse(base).netloc.replace("www.", "")
    links = [urljoin(base, a["href"]) for a in soup.find_all("a", href=True) if CAREER_WORDS.search(a["href"] + " " + a.get_text(" "))]   # nav + footer links
    links = [l for l in links if urlparse(l).scheme in ("http", "https")][:12]
    links += [f"https://{pre}.{host}" for pre in ("werkenbij", "careers", "jobs", "career", "vacatures")]
    links += [urljoin(base, p) for p in CAREER_PATHS]
    tried, sm_done = 0, False
    for l in dict.fromkeys(links):
        html = get(l); tried += 1
        if html: return l, html
        if tried >= 8 and not sm_done:       # direct guesses failed: ask the sitemap
            sm_done = True
            for sl in sitemap_career_urls(base):
                html = get(sl)
                if html: return sl, html
    return None

STUDENT_WORDS = re.compile(r"intern|stage|stagiair|student|graduate|trainee|early[- ]career|werkstudent|afstudeer|thesis|campus|young[- ]talent|starters?", re.I)
def student_pages(base, *htmls):
    """Links to dedicated internship / student / graduate pages found on the homepage or careers page, plus common paths."""
    out = []
    for h in htmls:
        for a in BeautifulSoup(h or "", "lxml").find_all("a", href=True):
            u = urljoin(base, a["href"]).split("#")[0]
            if urlparse(u).scheme in ("http", "https") and STUDENT_WORDS.search(a.get_text(" ") + " " + urlparse(u).path) and u.rstrip("/") != base.rstrip("/"): out.append(u)
    host = urlparse(base).netloc
    root = ".".join(host.replace("www.", "").split(".")[-2:]) if not host.endswith((".co.uk", ".com.au")) else ".".join(host.split(".")[-3:])
    out += [urljoin(base, p) for p in STUDENT_PATHS]
    out += [f"https://{sub}.{root}{p}" for sub in ("werkenbij", "careers", "jobs") for p in ("/stage", "/internships", "/studenten")]
    same = lambda u: urlparse(u).netloc.replace("www.", "").endswith(root)
    return list(dict.fromkeys(u for u in out if same(u)))[:STUDENT_MAX_PAGES]

STUDENT_PATHS = ("/internships", "/internship", "/stages", "/stage", "/stage-afstuderen", "/stages-en-afstuderen", "/afstuderen", "/students", "/student", "/studenten", "/graduates", "/graduate-programme",
                 "/early-careers", "/early-career", "/young-talent", "/young-professionals", "/traineeship", "/traineeships", "/careers/students", "/careers/internships", "/careers/early-careers", "/careers/graduates",
                 "/en/internships", "/en/students", "/nl/stage", "/nl/studenten", "/werken-bij/stage", "/werken-bij/studenten", "/vacatures/stage", "/jobs/internships", "/jobs/students", "/student-jobs", "/werkstudent")
STUDENT_MAX_PAGES = 14

def scan_student_pages(base, home_html, careers_html, known_urls):
    """Extra pass for internships: each student page is read via ATS embed -> JSON-LD -> job links -> headless browser. Postings are tagged kind=internship."""
    found = []
    for u in student_pages(base, home_html, careers_html)[:STUDENT_MAX_PAGES]:
        h = get(u)
        if not h: continue
        jobs = []
        a = detect_ats(h)
        if a and a[0] in ADAPTERS: jobs = ADAPTERS[a[0]](a[1]) or []
        jobs = jobs or jsonld_jobs(h, u) or generic_links(h, u)
        if len(jobs) < 3 and len(h) > 2000 and len(jobs) == 0: jobs, _ = render_scan(u)
        for j in jobs:
            if j["url"] not in known_urls and len(j["title"]) > 5:
                j["kind"] = "internship"; known_urls.add(j["url"]); found.append(j)
        if len(found) > 150: break
    return found

_ATS_KEY = {"workday": "myworkdayjobs", "teamtailor": "teamtailor", "personio": "personio", "bamboohr": "bamboohr", "homerun": "homerun", "greenhouse": "greenhouse", "lever": "lever.co", "ashby": "ashbyhq",
            "recruitee": "recruitee", "workable": "workable", "smartrecruiters": "smartrecruiters", "join": "join.com", "jobvite": "jobvite", "breezy": "breezy.hr", "carerix": "carerix", "otys": "otys", "emply": "emply", "icims": "icims"}
def detect_ats(html):
    html = (html or "")[:600_000]          # bounded input + bounded quantifiers: no regex blow-ups on huge inline blobs
    for ats, pat in ATS_PATTERNS:
        if _ATS_KEY.get(ats, "") not in html: continue
        m = re.search(pat, html)
        if m: return ats, ("|".join(m.groups()) if ats == "workday" else m.group(1))
    return None

def jsonld_jobs(html, base):
    out = []
    for sc in BeautifulSoup(html or "", "lxml").find_all("script", type="application/ld+json"):
        try: data = json.loads(sc.string or "")
        except Exception: continue
        items = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for it in items:
            if isinstance(it, dict) and it.get("@type") == "JobPosting":
                loc = it.get("jobLocation"); loc = loc[0] if isinstance(loc, list) and loc else loc
                addr = (loc or {}).get("address", {}) if isinstance(loc, dict) else {}
                out.append(dict(title=it.get("title", ""), location=addr.get("addressLocality", "") if isinstance(addr, dict) else "",
                                url=it.get("url") or base, description=_txt(it.get("description")), posted_at=it.get("datePosted")))
    return out

JOBLINK = re.compile(r"/(job|jobs|vacature|vacatures|vacancy|vacancies|position|positions|careers?|find-your-job)/[^/?#]+", re.I)
def generic_links(html, base):
    out, seen = [], set()
    for a in BeautifulSoup(html or "", "lxml").find_all("a", href=True):
        u = urljoin(base, a["href"]).split("#")[0]
        lines = [x for x in a.get_text("\n", strip=True).split("\n") if x and x.upper() not in ("NEW", "NIEUW")]
        t = lines[0] if lines else ""; loc = " ".join(lines[1:])[:120]
        if JOBLINK.search(urlparse(u).path) and 6 < len(t) < 160 and u not in seen:
            seen.add(u); out.append(dict(title=t, location=loc, url=u, description="", posted_at=None))
    idlike = [j for j in out if re.search(r"(-|/)j?\d{5,}(/|$)", urlparse(j["url"]).path)]
    if len(idlike) >= 5: out = idlike          # real postings carry an id; drops category/filter links
    return out[:400]

def _find_job_arrays(node, out, depth=0):
    """Walk captured XHR JSON for arrays of dicts that look like job postings."""
    if depth > 6: return
    if isinstance(node, list):
        ds = [x for x in node if isinstance(x, dict)]
        if len(ds) >= 3 and sum(1 for x in ds if any(k in x for k in ("title", "jobTitle", "name", "position", "text"))) >= len(ds) * 0.8 \
           and sum(1 for x in ds if any(k in x for k in ("url", "absolute_url", "hostedUrl", "applyUrl", "link", "id", "slug", "jobUrl", "externalPath", "path"))) >= len(ds) * 0.8:
            out.append(ds)
        for x in node[:50]: _find_job_arrays(x, out, depth + 1)
    elif isinstance(node, dict):
        for v in node.values(): _find_job_arrays(v, out, depth + 1)

PW = threading.Semaphore(max(1, BROWSER_SLOTS + 1))   # at most 4 headless browsers at once
def render_scan(url, click=()):
    with PW: return _render_scan(url, click)
def _render_scan(url, click=()):
    """Headless Chromium: render JS pages, intercept XHR/JSON job lists, then fall back to rendered DOM (JSON-LD, links). -> (jobs, final_html)"""
    try: from playwright.sync_api import sync_playwright
    except ImportError: return [], ""
    captured = []
    html = ""; pages_html = []
    try:
        with sync_playwright() as pw:
            b = pw.chromium.launch()
            pg = b.new_context(user_agent=UA, locale="en-NL").new_page()
            def on_resp(r):
                try:
                    if "json" in (r.headers.get("content-type") or "") and r.status == 200 and len(captured) < 30: captured.append((r.url, r.json()))
                except Exception: pass
            pg.on("response", on_resp)
            pg.goto(url, wait_until="networkidle", timeout=30000)
            try: pg.get_by_role("button", name="Accept all cookies").click(timeout=1500)
            except Exception: pass
            for label in click:   # site-specific filters, e.g. ASML "Internships"
                try:
                    pg.get_by_text(label, exact=True).first.click(timeout=3000); pg.wait_for_timeout(2500)
                except Exception: pass
            for _ in range(4):  # lazy lists / "load more"
                pg.mouse.wheel(0, 4000); pg.wait_for_timeout(600)
                for label in ("Load more", "Show more", "Meer laden", "Toon meer"):
                    try:
                        btn = pg.get_by_role("button", name=label)
                        if btn.count(): btn.first.click(timeout=1500); pg.wait_for_timeout(800)
                    except Exception: pass
            html = pg.content(); final = pg.url
            # numbered pagination (e.g. ASML: 27 pages): click 2,3,4… and collect each page's links
            pages_html = [html]
            try: pg.get_by_role("button", name="Accept all cookies").click(timeout=1500)
            except Exception: pass
            for n in range(2, 60):
                first = len(generic_links(pages_html[-1], url))
                if not first: break
                el = pg.get_by_role("button", name=str(n), exact=True)
                if not el.count(): el = pg.get_by_role("link", name=str(n), exact=True)
                if not el.count(): break
                try: el.first.click(timeout=2500); pg.wait_for_timeout(1300)
                except Exception: break
                pages_html.append(pg.content())
            b.close()
    except Exception:
        return [], html
    d = detect_ats(html)
    jobs = jsonld_jobs(html, url)
    for u, data in captured:
        arrs = []; _find_job_arrays(data, arrs)
        for arr in arrs:
            for x in arr:
                t = next((x[k] for k in ("title", "jobTitle", "name", "position", "text") if isinstance(x.get(k), str)), None)
                link = next((x[k] for k in ("absolute_url", "hostedUrl", "applyUrl", "jobUrl", "url", "link") if isinstance(x.get(k), str) and x[k].startswith("http")), None)
                loc = x.get("location") if isinstance(x.get("location"), str) else (x.get("locationsText") or x.get("city") or "")
                if t and link: jobs.append(dict(title=t, location=loc if isinstance(loc, str) else "", url=link, description="", posted_at=None))
    for h in pages_html[1:] if jobs else pages_html: jobs += generic_links(h, url)
    seen, uniq = set(), []
    for j in jobs:
        if j["url"] not in seen: seen.add(j["url"]); uniq.append(j)
    return uniq, html

def scan_company(c: dict):
    res = _scan_company(c)
    try:
        if res.get("website") and res.get("careers_url") and not (c.get("ats") or "").startswith("board:"):
            have = {j["url"] for j in res["jobs"]}
            extra = scan_student_pages(res["website"], get(res["website"], check_robots=False) or "", get(res["careers_url"]) or "", have)
            if extra: res["jobs"] = res["jobs"] + extra; res["note"] += f" + {len(extra)} from student pages"
    except Exception: pass
    return res

def _scan_company(c: dict):
    """-> dict(website, careers_url, ats, ats_slug, resolved_via, jobs, note)"""
    res = dict(website=c.get("website"), careers_url=c.get("careers_url"), ats=c.get("ats"), ats_slug=c.get("ats_slug"),
               resolved_via=c.get("resolved_via"), jobs=[], note="")
    # 1. known board
    if res["ats"] in ADAPTERS and res["ats_slug"]:
        jobs = ADAPTERS[res["ats"]](res["ats_slug"])
        if jobs: res.update(jobs=jobs, note=f"{res['ats']} API"); return res   # empty board: keep looking (stale boards are common)
    # 2. slug-guess every ATS API - only for companies with no saved career page / board yet. Re-guessing on every scan is what produced
    #    hundreds of 404/301 requests per run; a saved careers_url or ats_slug is reused instead (step 3 still re-detects a changed ATS).
    b = None if (res["careers_url"] or res["ats_slug"]) else find_board(c["name"])
    if b and b[2]:
        res.update(ats=b[0], ats_slug=b[1], jobs=b[2], resolved_via="ats-probe", note=f"{b[0]} API"); return res
    # 3. website -> careers page
    site = (res["website"], None) if res["website"] else None
    html = get(res["website"], check_robots=False) if res["website"] else None
    if not html:
        r = resolve_website(c["name"])
        if not r: res["note"] = "website not found"; return res
        res["website"], html, res["resolved_via"] = r
    cp = (res["careers_url"], get(res["careers_url"])) if res["careers_url"] else find_careers(res["website"], html)
    if not cp or not cp[1]: res["note"] = "no careers page found (or robots.txt disallows)"; return res
    res["careers_url"], chtml = cp
    d = detect_ats(chtml) or detect_ats(html)
    if d and d[0] in ADAPTERS:
        jobs = ADAPTERS[d[0]](d[1])
        if jobs:
            res.update(ats=d[0], ats_slug=d[1], jobs=jobs, note=f"{d[0]} API (found on careers page)"); return res
    jobs = jsonld_jobs(chtml, res["careers_url"])
    if jobs: res.update(jobs=jobs, ats="jsonld", note="schema.org JobPosting"); return res
    jobs = generic_links(chtml, res["careers_url"])
    if len(jobs) >= 30:
        res.update(jobs=jobs, ats="html", note="generic link extraction"); return res
    # 4. JS-rendered page: Playwright (network interception + rendered DOM)
    jobs, rhtml = render_scan(res["careers_url"])
    d = detect_ats(rhtml)
    if not jobs and d and d[0] in ADAPTERS:
        j2 = ADAPTERS[d[0]](d[1])
        if j2: res.update(ats=d[0], ats_slug=d[1], jobs=j2, note=f"{d[0]} API (found after JS render)"); return res
    if "asml.com" in res["careers_url"]:   # ASML's default list is "Jobs"; internships sit behind a filter
        extra, _h = render_scan(res["careers_url"], click=("Netherlands", "Internships"))
        have = {j["url"] for j in jobs}; jobs += [j for j in extra if j["url"] not in have]
    static = generic_links(chtml, res["careers_url"])
    if len(static) > len(jobs): jobs = static            # JS added nothing: keep the static links
    res.update(jobs=jobs, ats="playwright" if jobs else "html", note="rendered with Playwright (paginated)" if jobs else "careers page rendered, no postings found")
    return res

def fetch_detail(url):
    """Full posting text + date from the posting's own page: ATS detail APIs, then JSON-LD, then main text. Honours robots.txt."""
    out = {}
    m = re.match(r"https://jobs\.smartrecruiters\.com/([\w-]+)/(\d+)", url)
    if m:
        d = get(f"https://api.smartrecruiters.com/v1/companies/{m.group(1)}/postings/{m.group(2)}", True, False) or {}
        secs = (d.get("jobAd") or {}).get("sections") or {}
        out["description"] = "\n\n".join(_txt(v.get("text", "")) for v in secs.values() if isinstance(v, dict))
        out["posted_at"] = d.get("releasedDate"); return out
    m = re.match(r"(https://[\w-]+\.wd\d+\.myworkdayjobs\.com)/(?:[a-z]{2}-[A-Z]{2}/)?([\w-]+)(/job/.+)", url)
    if m:
        tenant = urlparse(m.group(1)).netloc.split(".")[0]
        d = get(f"{m.group(1)}/wday/cxs/{tenant}/{m.group(2)}{m.group(3)}", True, False) or {}
        i = d.get("jobPostingInfo") or {}
        return {"description": _txt(i.get("jobDescription")), "posted_at": i.get("startDate")}
    m = re.match(r"https://([\w-]+)\.bamboohr\.com/careers/(\d+)", url)
    if m:
        d = get(f"https://{m.group(1)}.bamboohr.com/careers/{m.group(2)}/detail", True, False) or {}
        o = (d.get("result") or {}).get("jobOpening") or {}
        return {"description": _txt(o.get("description")), "posted_at": o.get("datePosted")}
    html = get(url)
    if not html: return out
    for j in jsonld_jobs(html, url):
        if j.get("description"): return {"description": j["description"], "posted_at": j.get("posted_at")}
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "nav", "header", "footer"]): t.decompose()
    node = soup.find("main") or soup.find("article") or soup.body
    txt = re.sub(r"\n{3,}", "\n\n", node.get_text("\n", strip=True))[:15000] if node else ""
    return {"description": txt if len(txt) > 200 else ""}

def fetch_logo(base, html, cid):
    """Company logo from its own website: apple-touch-icon / icon links / og:image / favicon.ico. Cached to static/logos/<id>.<ext>. -> relative path or None"""
    os.makedirs(LOGO_DIR, exist_ok=True)
    soup = BeautifulSoup(html or "", "lxml"); cands = []
    for l in soup.find_all("link", href=True):
        rel = " ".join(l.get("rel", [])).lower()
        if "apple-touch-icon" in rel: cands.append((0, urljoin(base, l["href"])))
        elif "icon" in rel:
            m = re.search(r"(\d+)x", l.get("sizes", "") or ""); cands.append((1 if m and int(m.group(1)) >= 64 else 3, urljoin(base, l["href"])))
    og = soup.find("meta", property="og:image")
    if og and og.get("content"): cands.append((2, urljoin(base, og["content"])))
    cands.append((4, urljoin(base, "/favicon.ico")))
    for _, u in sorted(cands, key=lambda x: x[0])[:5]:
        try:
            _wait(urlparse(u).netloc)
            r = client.get(u)
            ct = (r.headers.get("content-type") or "").split(";")[0].lower()
            if r.status_code != 200 or not ct.startswith("image/") or not (400 < len(r.content) < 1_500_000): continue
            ext = {"image/png": "png", "image/jpeg": "jpg", "image/svg+xml": "svg", "image/x-icon": "ico", "image/vnd.microsoft.icon": "ico", "image/webp": "webp", "image/gif": "gif"}.get(ct)
            if not ext: continue
            with open(os.path.join(LOGO_DIR, f"{cid}.{ext}"), "wb") as f: f.write(r.content)
            return f"logos/{cid}.{ext}"
        except Exception: continue
    return None
