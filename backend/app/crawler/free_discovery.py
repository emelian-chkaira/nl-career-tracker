"""Free, key-less company discovery from open data (no search-engine scraping):
 - OpenStreetMap (Overpass API): Dutch IT/software/research/engineering offices with a website tag
 - Wikipedia categories + Wikidata official websites (Dutch tech company categories)
 - Wikipedia search (keyword -> related company pages -> Wikidata official website)
Wikimedia blocks python HTTP client fingerprints, so these calls go through curl."""
import json, re, subprocess, tempfile
UA = "nl-career-tracker/0.1"
def _curl(url, params=None, data=None, timeout=120):
    cmd = ["curl", "-s", "-m", str(timeout), "-A", UA, "-H", "Accept: application/json"]
    if data is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".q", delete=False) as f: f.write(data)
        cmd += ["--data-urlencode", f"data@{f.name}", url]
    else:
        cmd += ["-G", url]
        for k, v in (params or {}).items(): cmd += ["--data-urlencode", f"{k}={v}"]
    import time
    for attempt in range(3):
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10).stdout
        try: return json.loads(out)
        except Exception: time.sleep(2 * (attempt + 1))     # rate-limited / empty reply: back off and retry
    return {}

TECH_NAME = re.compile(r"tech|software|digital|data|labs?\b|systems|solutions|\bai\b|cloud|cyber|robot|engineering|electronic|semicon|photon|network|\bit\b|ict|informat|automation|analytics|platform|apps?\b|games?|studio|media|online|consult|nano|sensor|devops|security|fintech|pay", re.I)
def overpass_companies():
    q = '''[out:json][timeout:180];area["ISO3166-1"="NL"][admin_level=2]->.nl;
(nwr["office"~"^(it|software|research|telecommunication|engineering|company)$"]["website"](area.nl););out tags center 9000;'''
    out = []
    for e in _curl("https://overpass-api.de/api/interpreter", data=q, timeout=200).get("elements", []):
        t = e.get("tags", {}); name, site = t.get("name"), t.get("website") or t.get("contact:website")
        if not name or not site: continue
        if t.get("office") == "company" and not TECH_NAME.search(name): continue     # generic offices only when the name sounds tech
        if not site.startswith("http"): site = "https://" + site
        out.append((name, site))
    return out

WIKI_CATS = ["Software companies of the Netherlands", "Information technology companies of the Netherlands", "Technology companies of the Netherlands", "Internet companies of the Netherlands",
             "Electronics companies of the Netherlands", "Semiconductor companies of the Netherlands", "Video game companies of the Netherlands", "Financial technology companies",
             "Computer companies of the Netherlands", "Telecommunications companies of the Netherlands", "Aerospace companies of the Netherlands", "Dutch software companies",
             "Technology companies based in Amsterdam", "Companies based in Eindhoven", "Companies based in Delft", "Companies based in Utrecht", "Software companies based in Amsterdam",
             "Information technology consulting firms of the Netherlands", "Defence companies of the Netherlands", "Biotechnology companies of the Netherlands", "Mobile phone companies of the Netherlands",
             "Dutch brands", "Online marketplaces of the Netherlands", "E-commerce companies of the Netherlands", "Companies based in Rotterdam", "Companies based in Groningen", "Companies based in Enschede"]
def _wd_sites(qids):
    out = {}
    for i in range(0, len(qids), 40):
        d = _curl("https://www.wikidata.org/w/api.php", {"action": "wbgetentities", "ids": "|".join(qids[i:i + 40]), "props": "claims|labels", "languages": "en", "format": "json"})
        for qid, e in (d.get("entities") or {}).items():
            try: site = e["claims"]["P856"][0]["mainsnak"]["datavalue"]["value"]
            except Exception: continue
            out[qid] = ((e.get("labels") or {}).get("en") or {}).get("value"), site
    return out
def _titles_to_companies(titles):
    qids = {}
    for i in range(0, len(titles), 40):
        d = _curl("https://en.wikipedia.org/w/api.php", {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "titles": "|".join(titles[i:i + 40]), "format": "json", "redirects": 1})
        for p in (d.get("query", {}).get("pages") or {}).values():
            q = (p.get("pageprops") or {}).get("wikibase_item")
            if q: qids[q] = p["title"]
    return [(name or qids[q], site) for q, (name, site) in _wd_sites(list(qids)).items()]
NL_WIKI_CATS = ["Nederlands softwarebedrijf", "Nederlands internetbedrijf", "Nederlands bedrijf in de informatietechnologie", "Nederlands elektronicabedrijf", "Nederlands computerspelontwikkelaar",
                "Nederlands telecommunicatiebedrijf", "Nederlandse start-up", "Nederlands halfgeleiderbedrijf", "Nederlands luchtvaart- en ruimtevaartbedrijf", "Nederlands technologiebedrijf"]
def _wp_titles(host, cats, prefix):
    titles = []
    for c in cats:
        d = _curl(f"https://{host}/w/api.php", {"action": "query", "list": "categorymembers", "cmtitle": prefix + c.replace(" ", "_"), "cmlimit": 500, "cmnamespace": 0, "format": "json"})
        titles += [m["title"] for m in d.get("query", {}).get("categorymembers", [])]
    return titles
def wikipedia_categories():
    out = _titles_to_companies(list(dict.fromkeys(_wp_titles("en.wikipedia.org", WIKI_CATS, "Category:"))))
    try:
        qids = {}
        titles = list(dict.fromkeys(_wp_titles("nl.wikipedia.org", NL_WIKI_CATS, "Categorie:")))
        for i in range(0, len(titles), 40):
            d = _curl("https://nl.wikipedia.org/w/api.php", {"action": "query", "prop": "pageprops", "ppprop": "wikibase_item", "titles": "|".join(titles[i:i + 40]), "format": "json", "redirects": 1})
            for p in (d.get("query", {}).get("pages") or {}).values():
                q = (p.get("pageprops") or {}).get("wikibase_item")
                if q: qids[q] = p["title"]
        out += [(n or qids[q], w) for q, (n, w) in _wd_sites(list(qids)).items()]
    except Exception: pass
    return out
def wikipedia_search(keyword, limit=30):
    """free keyword -> company pages (Netherlands) -> official websites"""
    d = _curl("https://en.wikipedia.org/w/api.php", {"action": "query", "list": "search", "srsearch": f"{keyword} company Netherlands headquartered", "srlimit": limit, "format": "json"})
    return _titles_to_companies([r["title"] for r in d.get("query", {}).get("search", [])])


def europeantechmap(progress=None, max_pages=40):
    """europeantechmap.eu (robots.txt allows crawling, /claim/ excluded): Netherlands listing pages -> company pages -> JSON-LD provider name + website.
    Polite: robots honoured and 1 request/second via discovery.get."""
    from . import discovery
    base = "https://europeantechmap.eu"
    slugs = []
    for pg in range(1, max_pages + 1):
        html = discovery.get(f"{base}/country/netherlands?page={pg}")
        found = [x for x in dict.fromkeys(re.findall(r'href="/company/([^"#?]+)"', html or "")) if x not in slugs]
        if not found: break
        slugs += found
    out = []
    for i, sl in enumerate(slugs):
        html = discovery.get(f"{base}/company/{sl}")
        if progress: progress(f"europeantechmap: {i + 1}/{len(slugs)} company pages read")
        if not html: continue
        for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S):
            try: d = json.loads(m)
            except Exception: continue
            if d.get("@type") == "SoftwareApplication":
                pr = d.get("provider") or {}
                name = (pr.get("name") or d.get("name") or "").strip(); site = (pr.get("url") or "").strip()
                name = re.sub(r"\s+(B\.?V\.?|N\.?V\.?)$", "", name, flags=re.I)
                if name and site.startswith("http"): out.append((name, site))
                break
    return out


CITIES_NL = ["Amsterdam", "Rotterdam", "Den Haag", "Utrecht", "Eindhoven", "Groningen", "Tilburg", "Almere", "Breda", "Nijmegen", "Apeldoorn", "Haarlem", "Arnhem", "Enschede", "Amersfoort", "Zaanstad", "'s-Hertogenbosch",
 "Haarlemmermeer", "Zwolle", "Zoetermeer", "Leiden", "Leeuwarden", "Maastricht", "Dordrecht", "Ede", "Alphen aan den Rijn", "Alkmaar", "Emmen", "Delft", "Venlo", "Deventer", "Sittard-Geleen", "Helmond", "Oss", "Amstelveen",
 "Hilversum", "Heerlen", "Hengelo", "Purmerend", "Roosendaal", "Schiedam", "Lelystad", "Spijkenisse", "Leidschendam-Voorburg", "Hoorn", "Gouda", "Vlaardingen", "Almelo", "Assen", "Capelle aan den IJssel", "Veenendaal", "Katwijk",
 "Zeist", "Nieuwegein", "Hoofddorp", "Rijswijk", "Veldhoven", "Wageningen", "Bussum", "Woerden", "Houten", "Zwijndrecht", "Heerhugowaard", "Middelburg", "Terneuzen", "Vlissingen", "Doetinchem", "Harderwijk", "Barneveld", "Soest",
 "Waalwijk", "Weert", "Roermond", "Kampen", "Meppel", "Hardenberg", "Hoogeveen", "Bergen op Zoom", "Etten-Leur", "Oosterhout", "Boxtel", "Best", "Son en Breugel", "Nuenen", "Geldrop", "Uden", "Cuijk", "Wijchen", "Ede", "Epe",
 "Baarn", "De Bilt", "Bilthoven", "Driebergen-Rijsenburg", "Naarden", "Weesp", "Diemen", "Badhoevedorp", "Schiphol", "Sassenheim", "Voorschoten", "Wassenaar", "Noordwijk", "Lisse", "Gorinchem", "Culemborg", "Tiel", "Zutphen",
 "Winterswijk", "Dronten", "Emmeloord", "Heerenveen", "Drachten", "Sneek", "Den Helder", "Beverwijk", "IJmuiden", "Velsen", "Krommenie", "Zaandam", "Waddinxveen", "Nieuwkoop", "Leusden", "Nunspeet", "Elburg", "Vught", "Goirle", "Oisterwijk"]
def overpass_cities(progress=None):
    """OpenStreetMap, city by city (beats the single-query size cap): tech-ish offices with a website + their city/address."""
    import time
    out, seen = [], set()
    for i, city in enumerate(dict.fromkeys(CITIES_NL)):
        q = f'''[out:json][timeout:90];
area["name"="{city}"]["boundary"="administrative"]["admin_level"~"^(8|9)$"]->.a;
(nwr["office"~"^(it|software|research|telecommunication|engineering|company|consulting)$"]["website"](area.a);
 nwr["industrial"]["website"]["name"](area.a); nwr["shop"="computer"]["website"](area.a); nwr["craft"="electronics_repair"]["website"](area.a););
out tags center 3000;'''
        try: els = _curl("https://overpass-api.de/api/interpreter", data=q, timeout=100).get("elements", [])
        except Exception: els = []
        for e in els:
            t = e.get("tags", {}); name, site = t.get("name"), t.get("website") or t.get("contact:website")
            if not name or not site: continue
            if t.get("office") in ("company", "consulting") or t.get("industrial") or t.get("shop") or t.get("craft"):
                if not TECH_NAME.search(name): continue
            if not site.startswith("http"): site = "https://" + site
            key = (name.lower(), site.lower())
            if key in seen: continue
            seen.add(key)
            addr = " ".join(x for x in [t.get("addr:street"), t.get("addr:housenumber"), t.get("addr:postcode")] if x)
            out.append((name, site, t.get("addr:city") or city, addr, t.get("office") or t.get("industrial") or t.get("shop")))
        if progress: progress(f"OpenStreetMap by city: {i + 1}/{len(set(CITIES_NL))} cities · {len(out)} companies")
        time.sleep(2)
    return out
