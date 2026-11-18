"""Wikidata: Dutch software/IT companies with an official website (open data, CC0)."""
WD_QUERIES = ["""SELECT DISTINCT ?cLabel ?site WHERE { VALUES ?t { wd:Q1058914 wd:Q18388277 wd:Q1478276 wd:Q2088357 wd:Q1137109 } ?c wdt:P31 ?t; wdt:P17 wd:Q55; wdt:P856 ?site. FILTER NOT EXISTS { ?c wdt:P576 ?end } SERVICE wikibase:label { bd:serviceParam wikibase:language "en,nl". } } LIMIT 3000""",
 """SELECT DISTINCT ?cLabel ?site WHERE { ?c wdt:P17 wd:Q55; wdt:P856 ?site; wdt:P452 ?ind. VALUES ?ind { wd:Q638608 wd:Q11661 wd:Q1334 wd:Q2352616 wd:Q7397 wd:Q196718 wd:Q2342494 wd:Q1348006 wd:Q1665595 wd:Q11660 wd:Q1297322 wd:Q1073 wd:Q1458157 } FILTER NOT EXISTS { ?c wdt:P576 ?end } SERVICE wikibase:label { bd:serviceParam wikibase:language "en,nl". } } LIMIT 3000"""]

import json, re, subprocess, tempfile


def fetch() -> list[tuple[str, str]]:
    out = []
    for qy in WD_QUERIES:
        try:   # Wikimedia blocks Python HTTP client fingerprints; curl is accepted
            with tempfile.NamedTemporaryFile("w", suffix=".rq", delete=False) as f: f.write(qy)
            raw = subprocess.run(["curl", "-s", "-m", "110", "-G", "https://query.wikidata.org/sparql", "-H", "Accept: application/json", "-A", "nl-career-tracker/0.3",
                                  "--data-urlencode", f"query@{f.name}"], capture_output=True, text=True, timeout=120).stdout
            d = json.loads(raw)
        except Exception: continue
        for b in d["results"]["bindings"]:
            name = b["cLabel"]["value"]
            if not re.fullmatch(r"Q\d+", name): out.append((name, b["site"]["value"]))
    return out
