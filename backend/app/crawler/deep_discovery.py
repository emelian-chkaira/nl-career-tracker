"""Extra open-data sweeps for IT companies in the Netherlands (all CC0/ODbL data; no scraping of search engines)."""
import json, subprocess, tempfile, re


def _sparql(q: str) -> list[tuple[str, str]]:
    with tempfile.NamedTemporaryFile("w", suffix=".rq", delete=False) as f: f.write(q)
    out = []
    try:
        raw = subprocess.run(["curl", "-s", "-m", "170", "-G", "https://query.wikidata.org/sparql", "-H", "Accept: application/json", "-A", "nl-career-tracker/0.3", "--data-urlencode", f"query@{f.name}"], capture_output=True, text=True, timeout=180).stdout
        for b in json.loads(raw)["results"]["bindings"]:
            n = b["cLabel"]["value"]
            if not re.fullmatch(r"Q\d+", n): out.append((n, b["site"]["value"]))
    except Exception: pass
    return out


ROOTS = ["Q11661", "Q638608", "Q1334", "Q7397", "Q196718", "Q2352616", "Q11660", "Q1073", "Q2095", "Q1668024", "Q638", "Q3918", "Q177719", "Q1129194", "Q21198", "Q43229", "Q1325963", "Q83267", "Q8068"]


def wikidata_industry():
    """Dutch companies whose industry is IT or a direct sub-industry (one query per root: the property-path version times out on WDQS)."""
    out = {}
    for r in ROOTS:
        for path in ("wdt:P452", "wdt:P452/wdt:P279"):
            q = f"""SELECT DISTINCT ?cLabel ?site WHERE {{ ?c wdt:P17 wd:Q55; wdt:P856 ?site; {path} wd:{r}. FILTER NOT EXISTS {{ ?c wdt:P576 ?end }}
              SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,nl". }} }} LIMIT 3000"""
            for n, w in _sparql(q): out[n] = w
    return list(out.items())


def wikidata_by_region():
    """Companies of Dutch origin whose country is NL and instance is software/IT/startup-like (one hop only)."""
    out = {}
    for t in ("Q1058914", "Q18388277", "Q2088357", "Q1137109", "Q1478276", "Q15265344", "Q4830453", "Q5105283", "Q1294765", "Q783794"):
        q = f"""SELECT DISTINCT ?cLabel ?site WHERE {{ ?c wdt:P17 wd:Q55; wdt:P856 ?site; wdt:P31 wd:{t}. FILTER NOT EXISTS {{ ?c wdt:P576 ?end }}
          SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en,nl". }} }} LIMIT 5000"""
        for n, w in _sparql(q): out[n] = w
    return list(out.items())


NAME_RE = r"(software|digital|data|cyber|cloud|ict|automation|robotics|semicon|photonic|embedded|devops|fintech|saas|apps|game|studio|webdesign|webdevelop|web ?shop|hosting|internet|networks?|systems|informatica|informatie|technolog|tech|labs|analytics|platform|solutions|interactive|online|mobile|security|software ?house|consultancy|engineering|electronics|sensor|iot)"


def osm_names():
    return []   # name-regex Overpass query times out on the public instance; per-city sweep in free_discovery.overpass_cities covers this
    from app.crawler.free_discovery import _curl, TECH_NAME
    q = f'''[out:json][timeout:240];area["ISO3166-1"="NL"][admin_level=2]->.nl;
(nwr["name"~"{NAME_RE}",i]["website"]["office"](area.nl); nwr["name"~"{NAME_RE}",i]["website"]["building"="commercial"](area.nl);
 nwr["name"~"{NAME_RE}",i]["website"]["industrial"](area.nl); nwr["name"~"{NAME_RE}",i]["website"]["craft"](area.nl); nwr["name"~"{NAME_RE}",i]["contact:website"]["office"](area.nl););
out tags center 12000;'''
    out = []
    for e in _curl("https://overpass-api.de/api/interpreter", data=q, timeout=260).get("elements", []):
        t = e.get("tags", {}); name, site = t.get("name"), t.get("website") or t.get("contact:website")
        if not name or not site: continue
        if not site.startswith("http"): site = "https://" + site
        out.append((name, site))
    return out


def _subcats(host, root, prefix, depth=3, cap=400):
    from app.crawler.free_discovery import _curl
    seen, frontier, titles = {root}, [root], []
    for _ in range(depth):
        nxt = []
        for c in frontier:
            d = _curl(f"https://{host}/w/api.php", {"action": "query", "list": "categorymembers", "cmtitle": prefix + c.replace(" ", "_"), "cmlimit": 500, "cmtype": "page|subcat", "format": "json"})
            for m in d.get("query", {}).get("categorymembers", []):
                if m["ns"] == 14:
                    sc = m["title"].split(":", 1)[1]
                    if sc not in seen and len(seen) < cap: seen.add(sc); nxt.append(sc)
                elif m["ns"] == 0: titles.append(m["title"])
        frontier = nxt
    return titles


def wikipedia_deep():
    """Wikipedia category trees (English + Dutch, 3 levels deep) -> Wikidata official websites."""
    from app.crawler.free_discovery import _titles_to_companies, _wd_sites, _curl
    en = ["Software companies of the Netherlands", "Information technology companies of the Netherlands", "Technology companies of the Netherlands", "Internet companies of the Netherlands",
          "Dutch companies by industry", "Companies of the Netherlands by industry", "Dutch startups", "Defunct software companies of the Netherlands"]
    out = _titles_to_companies(list(dict.fromkeys(t for r in en[:-1] for t in _subcats("en.wikipedia.org", r, "Category:"))))
    nlr = ["Nederlands bedrijf in de informatietechnologie", "Nederlands softwarebedrijf", "Nederlands internetbedrijf", "Nederlands technologiebedrijf", "Nederlands telecommunicatiebedrijf", "Nederlandse start-up"]
    titles = list(dict.fromkeys(t for r in nlr for t in _subcats("nl.wikipedia.org", r, "Categorie:")))
    qids = {}
    for i in range(0, len(titles), 40):
        d = _curl("https://nl.wikipedia.org/w/api.php", {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "titles": "|".join(titles[i:i + 40]), "format": "json", "redirects": 1})
        for p in (d.get("query", {}).get("pages") or {}).values():
            q = (p.get("pageprops") or {}).get("wikibase_item")
            if q: qids[q] = p["title"]
    out += [(n or qids[q], w) for q, (n, w) in _wd_sites(list(qids)).items()]
    return out
