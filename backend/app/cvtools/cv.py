"""CV engine: extract a structured CV from PDF/DOCX/text, tailor it to one job, and draft a cover letter.

Design rules
 - Stateless and private: nothing is stored server-side; the browser keeps the CV and sends it with each request.
 - No fabrication: tailoring only re-orders, emphasises and selects what is already in the CV. Job requirements the CV lacks are
   reported as "gaps" for the user to decide on; they are never added as skills.
 - Deterministic rule-based core (no API key needed). An optional LLM polish pass exists (`polish`) but is off unless the operator sets
   ANTHROPIC_API_KEY *and* the request asks for it, because it sends the CV to a third party."""
import io, re, zipfile, html as _html
from app.crawler import nl
from app.crawler.search import ONTOLOGY

MAX_BYTES = 3_000_000

# ---------------------------------------------------------------- text extraction
def extract_text(data: bytes, filename: str = "") -> str:
    if len(data) > MAX_BYTES: raise ValueError("file too large (max 3 MB)")
    name = (filename or "").lower()
    if data[:4] == b"%PDF" or name.endswith(".pdf"):
        from pypdf import PdfReader
        r = PdfReader(io.BytesIO(data))
        if r.is_encrypted: raise ValueError("encrypted PDF")
        text = "\n".join((p.extract_text() or "") for p in r.pages[:12])
    elif data[:2] == b"PK" or name.endswith(".docx"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if sum(i.file_size for i in z.infolist()) > 30_000_000: raise ValueError("document too large")   # zip-bomb guard
            xml = z.read("word/document.xml").decode("utf8", "ignore")
        xml = re.sub(r"</w:p>", "\n", xml); xml = re.sub(r"<w:tab/>", "\t", xml); xml = re.sub(r"<[^>]+>", "", xml)
        text = _html.unescape(xml)
    else:
        text = data.decode("utf8", "ignore")
    text = text.replace("\r", "").replace(" ", " ")
    text = re.sub(r"[•●▪◦‣∙·]\s*", "- ", text)
    text = re.sub(r"[ \t]+\n", "\n", text); text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

# ---------------------------------------------------------------- vocabulary
_EXTRA = """python java javascript typescript c# c++ go golang rust kotlin swift swiftui dart flutter react react-native vue angular svelte next.js node.js express django flask fastapi spring .net asp.net php laravel ruby rails scala
sql postgresql postgres mysql mongodb redis elasticsearch kafka rabbitmq graphql rest grpc docker kubernetes terraform ansible jenkins gitlab github-actions ci/cd aws azure gcp linux bash git
html css sass tailwind figma pandas numpy scikit-learn pytorch tensorflow spark airflow dbt snowflake bigquery tableau power-bi excel
machine-learning deep-learning nlp llm computer-vision mlops data-science data-engineering microservices agile scrum jira testing selenium cypress playwright junit pytest firebase supabase android ios xcode
unity unreal embedded rtos c matlab simulink fpga verilog vhdl cad solidworks labview sap salesforce""".split()
def _vocab():
    v = set(w.replace("-", " ") for w in _EXTRA)
    for k, (al, rel) in ONTOLOGY.items(): v.add(k); v.update(al); v.update(rel)
    return {t for t in v if 1 < len(t) < 30 and t not in ("job", "work", "software", "technical", "engineering", "product", "design", "sales", "finance", "marketing")}
_ROLE = re.compile(r"developer|engineer|intern|trainee|graduate|analyst|scientist|manager|designer|owner|tester|thesis|afstudeer|stage|stagiair|junior|entry|student|programmer|ontwikkelaar|reporting|analytics|content|brand|growth|campaign|compliance|risk|executive|specialist|consultant|architect|\bsre\b|site reliability|platform|solutions|infrastructure|server-side|\bapi\b|cloud$", re.I)
_GENERIC_TERMS = {"roadmap", "stakeholder", "financial", "social media", "seo", "audit", "accounting", "treasury", "fp&a", "customer success", "business development", "user research", "visual design", "interaction design", "penetration", "soc", "iam", "kpi", "crm", "rest", "api", "mobile", "apple", "app", "ui", "ux", "ml", "ai", "js", "ts", "ci/cd", "testing", "automation", "agile", "scrum", "reporting", "statistics", "data", "web", "java script", "go developer"}
VOCAB = {t for t in _vocab() if not _ROLE.search(t) and t not in _GENERIC_TERMS} | {"rest api", "rest apis", "machine learning", "ci/cd", "ai", "ml", "agile", "scrum", "cloud", "mobile development"}
_SHORT = {"c", "go", "r", "ml", "ai", "qa", "ui", "ux", "js", "ts", "sre", "sap", "bi"}

_CASE = {"ios": "iOS", "javascript": "JavaScript", "typescript": "TypeScript", "postgresql": "PostgreSQL", "mongodb": "MongoDB", "graphql": "GraphQL", "github": "GitHub", "gitlab": "GitLab",
         "node.js": "Node.js", "next.js": "Next.js", "react native": "React Native", "react-native": "React Native", "fastapi": "FastAPI", "machine learning": "Machine Learning", "nlp": "NLP",
         "llm": "LLM", "mlops": "MLOps", "aws": "AWS", "gcp": "GCP", "html": "HTML", "css": "CSS", "sql": "SQL", "mysql": "MySQL", "c#": "C#", "c++": ".C++".lstrip("."), ".net": ".NET", "asp.net": "ASP.NET", "rest api": "REST API", "rest apis": "REST APIs", "ci/cd": "CI/CD", "ai": "AI", "ml": "ML"}
def pretty(t: str) -> str: return _CASE.get(t, t if len(t) <= 1 else (t.upper() if len(t) <= 2 else t[0].upper() + t[1:]))

def find_terms(text: str) -> list[str]:
    """Vocabulary terms present in `text` (whole-word, case-insensitive), ordered by first appearance."""
    low = " " + re.sub(r"[^\w+#./ -]", " ", (text or "").lower()) + " "
    hits = []
    for t in VOCAB:
        pat = r"(?<![\w+#.])" + re.escape(t) + r"(?![\w+#]|\.\w)"
        m = re.search(pat, low)
        if m: hits.append((m.start(), t))
    return [t for _, t in sorted(hits)]

# ---------------------------------------------------------------- languages / footers / references
LANGS = ("arabic english dutch german french spanish italian portuguese russian ukrainian polish turkish chinese mandarin cantonese japanese korean hindi urdu persian farsi hebrew greek swedish norwegian danish finnish "
         "czech slovak hungarian romanian bulgarian serbian croatian bosnian albanian armenian kurdish bengali tamil telugu vietnamese thai indonesian malay tagalog swahili afrikaans nederlands engels duits frans spaans arabisch turks").split()
_LANG_RE = re.compile(r"(?<![\w])(" + "|".join(LANGS) + r")(?![\w])\s*(?:[:(–—-]\s*)?", re.I)
_FOOTER_RE = re.compile(r"(?:[^\W\d_]+[ ]){1,3}[^\W\d_]+\s[-–—|]\s*(?:curriculum vitae|resume|résumé|cv)\b(?:\s*[-–—|]\s*\S+)?", re.I)
_REF_RE = re.compile(r"\b(academic |professional |personal )?references?\b\s*:?", re.I)
_LEVEL_TAIL = re.compile(r"\s*[,;.\-–—]*\s*(view (the )?letter|available (on|upon) request)\.?$", re.I)

def strip_footer(text: str) -> str:
    """Remove running page footers such as 'Jane Doe - Curriculum Vitae - jane.dev'."""
    return _FOOTER_RE.sub("", text)

def parse_languages(lines: list[str]) -> list[str]:
    """Language section -> ['Arabic: native', 'English: B2 overall, C1 listening – [Oxford certificate](url)'].
    Only entries that start with a real language name are kept; references and page footers that share the block are cut off."""
    raw = "\n".join(x.strip().lstrip("\x01\x02") for x in lines if x.strip())
    raw = "\n".join(strip_footer(l) for l in raw.split("\n"))
    keep = []
    for l in raw.split("\n"):
        m = _REF_RE.search(l)
        if m: l = l[:m.start()]
        if l.strip(" -–—•;"): keep.append(l)
    raw = " ; ".join(keep)
    segs = [x.strip() for x in re.split(r"\s*[•;]\s*|\s+-\s+(?=(?:" + "|".join(LANGS) + r")\b)", raw, flags=re.I) if x.strip(" -–—,.")]
    merged = []
    for sg in segs:                                                      # a segment that is not a language is the detail of the previous one
        if merged and not _LANG_RE.match(sg): merged[-1] += (" – " + sg if LINK_RE.match(sg) else " (" + sg.strip(" ,.-") + ")")
        else: merged.append(sg)
    out = []
    for sg in merged:
        m = _LANG_RE.match(sg)
        if not m: continue
        lvl = re.sub(r"\s+-\s+", " – ", sg[m.end():]).strip(" ;,.-–—•")
        lvl = re.sub(r"\.\]\(", "](", lvl)
        out.append(f"{m.group(1).capitalize()}: {lvl}" if lvl else m.group(1).capitalize())
    if not out:                                                          # no recognisable language names: keep short plain items only
        out = [x.strip(" -.") for x in re.split(r"[;,\n•]+", raw) if 2 <= len(x.strip(" -.")) <= 40]
    return list(dict.fromkeys(out))[:10]

def extract_references(lines: list[str]) -> list[str]:
    """'Academic reference: Dr X, Head, Uni - [View letter](url)' lines, kept whole (link included)."""
    out = []
    for l in lines:
        l = strip_footer(l.strip().lstrip("\x01\x02"))
        m = _REF_RE.search(l)
        if not m: continue
        t = re.sub(r"\s+-\s+(?=\[)", " – ", l[m.start():]); t = re.sub(r"\.\]\(", "](", t).strip()
        if len(t) > 14: out.append(t[:300])
    return list(dict.fromkeys(out))[:4]

# ---------------------------------------------------------------- parsing
HEAD = {
    "summary": r"(professional )?(summary|profile|about( me)?|objective|personal statement|introduction)",
    "experience": r"(work |professional |relevant )?(experience|employment|work history|career|internships?)",
    "education": r"(education|academic background|studies|qualifications)",
    "skills": r"((technical|key|core|it) )?(skills|competenc(e|ies)|technologies|tech stack|expertise)",
    "projects": r"(personal |academic |selected )?projects?",
    "languages": r"languages?",
    "certifications": r"(certifications?|certificates|courses|awards)",
    "other": r"(interests|hobbies|references|volunteering|activities|publications)",
}
HEAD_RE = {k: re.compile(rf"^\s*{v}\s*:?\s*$", re.I) for k, v in HEAD.items()}
DATE_RE = re.compile(r"((jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(19|20)\d{2}\s*(-|–|—|to)\s*(((jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+)?(19|20)\d{2}|present|now|current|heden)", re.I)

LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_MON = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_SEG = re.compile(rf"^(?:{_MON}\s+)?(?:\d{{1,2}}(?:\s*-\s*\d{{1,2}})?,\s*)?(?:19|20)\d{{2}}(?:\s*-\s*(?:(?:{_MON}\s+)?(?:19|20)\d{{2}}|present|now|current|heden))?(?:\s*\(.*\))?$", re.I)
def plain(s: str) -> str:
    """Text with link markup / bold markers removed (for scoring, search and display)."""
    return re.sub(r"\s+", " ", LINK_RE.sub(r"\1", (s or "").replace("**", ""))).strip()
def _only_links(s: str) -> bool:
    return bool(LINK_RE.search(s)) and not re.sub(r"[\s•|·,;/-]+", "", LINK_RE.sub("", s))
def _tech(desc: str):
    """'Sentence. - React, Vite' -> ('Sentence.', 'React, Vite')"""
    m = re.search(r"^(.*[.!?;)\d%])\s+-\s+([^!?]{2,160})$", desc)
    if m and not re.search(r"\.\s", m.group(2)) and not m.group(2).rstrip().endswith(".") and ("," in m.group(2) or len(m.group(2).split()) <= 4): return m.group(1).strip(), m.group(2).strip()
    return desc, ""

def _parse_head(head: str) -> dict:
    """One entry heading row -> {kind, title, date, meta, links}. Columns arrive separated by two spaces."""
    segs = [x.strip() for x in re.split(r"\s{2,}", head.strip()) if x.strip()]
    date = next((x for x in reversed(segs[1:] if len(segs) > 1 else segs) if DATE_SEG.match(plain(x))), "")
    if not date and segs and DATE_RE.search(plain(segs[-1])) and len(segs) > 1: date = segs[-1]
    if date:
        title = " ".join(x for x in segs if x != date).strip()
        return {"kind": "entry", "title": title, "date": date, "meta": "", "links": []}
    if len(segs) >= 2 or (segs and LINK_RE.search(segs[0]) and re.search(r"\)\s+\S", segs[0])):
        title = segs[0]; rest = segs[1:]; meta = ""; links = []
        if LINK_RE.search(title) and not rest:                           # 'Title [A](u) • [B](v) meta' collapsed to one segment
            i = title.index("["); rest = [title[i:]]; title = title[:i].strip()
        for x in rest:
            if LINK_RE.search(x):
                tail = re.split(r"\)\s*(?:•\s*)?(?=[^\[\s•])", x)                  # trailing text after the last link is the meta
                m = re.search(r"\)\s+([^\[\]()]+)$", x)
                if m and not LINK_RE.search(m.group(1)): meta = (meta + " " + m.group(1)).strip(); x = x[:m.start() + 1]
                links += [{"label": l, "url": u} for l, u in LINK_RE.findall(x)]
            else: meta = (meta + " " + x).strip()
        return {"kind": "project", "title": title, "date": "", "meta": meta, "links": links}
    return {"kind": "plain", "title": segs[0] if segs else head, "date": "", "meta": "", "links": []}

def _blocks(lines: list[str]) -> list[dict]:
    """Group a section into entries. Each block: heading (legacy one-line form), title / place / date / meta, links, desc, tech, bullets, kind."""
    out, cur = [], None
    def new(head, forced=False):
        h = _parse_head(head)
        return {"heading": "", "bullets": [], "title": h["title"], "place": "", "date": h["date"], "meta": h["meta"], "links": h["links"], "desc": "", "tech": "", "kind": h["kind"], "_head": head}
    def close():
        nonlocal cur
        if not cur: return
        if cur["kind"] == "project" or cur["kind"] == "plain":
            d = cur["desc"]
            if len(cur["bullets"]) == 1 and d and "," in cur["bullets"][0] and not re.search(r"[.!?]$", cur["bullets"][0]) and cur["kind"] == "project":
                d, cur["tech"] = d, cur["bullets"].pop(0)
            d, t = _tech(d)
            cur["desc"] = d; cur["tech"] = cur["tech"] or t
        cur["heading"] = " | ".join(x for x in (plain(cur["title"]), plain(cur["place"])) if x) + (("  " + plain(cur["date"])) if cur["date"] else "")
        cur.pop("_head", None); out.append(cur); cur = None
    for ln in lines:
        bold = ln.lstrip().startswith("\x01")
        s = ln.strip().lstrip("\x01\x02").strip().replace("\u2013", "-").replace("\u2014", "-")
        if not s:
            if cur and (cur["bullets"] or cur["desc"]) and not cur.get("_sticky"): close()
            continue
        is_bullet = s.startswith(("- ", "* "))
        starts_entry = (bold or bool(DATE_RE.search(plain(s)))) and not is_bullet
        if starts_entry or cur is None and not is_bullet:
            close(); cur = new(s); continue
        if cur is None: cur = new("")
        if is_bullet:
            if cur["kind"] == "project" and cur["desc"] and not cur["bullets"] and not cur["tech"] and re.fullmatch(r"- [^.!?]{2,160}", s) and "," in s: cur["tech"] = s[2:].strip()
            else: cur["bullets"].append(s[2:].strip())
        elif cur["bullets"]: cur["bullets"][-1] += " " + s                       # wrapped bullet line
        elif _only_links(s): cur["links"] += [{"label": l, "url": u} for l, u in LINK_RE.findall(s)]
        elif cur["kind"] == "entry" and not cur["place"] and not cur["desc"]: cur["place"] = s
        elif cur["kind"] == "plain" and not cur["place"] and not cur["desc"]: cur["place"] = s
        elif (cur["kind"] == "project" and cur["desc"].rstrip().endswith(".") and "," in s and len(s) <= 90 and not re.search(r"[.!?]$", s)
              and not LINK_RE.search(s) and all(len(x.split()) <= 4 for x in s.split(","))): cur["tech"] = s
        else: cur["desc"] = (cur["desc"] + " " + s).strip()
    close()
    for b in out:
        if b["kind"] == "project" and not b["desc"] and b["place"]: b["desc"], b["place"] = b["place"], ""
        if b["kind"] == "project": b["desc"], t = _tech(b["desc"]); b["tech"] = b["tech"] or t
        b["desc"] = b["desc"].replace("** **", " ")
    return [b for b in out if b["title"] or b["bullets"] or b["desc"]]

def _skill_groups(lines: list[str]) -> list[dict]:
    """Skill rows -> [{label, items}]. Accepts 'Label: a, b' and layout rows (bold label column + items column, wrapped continuation lines)."""
    groups = []
    for l in lines:
        raw = l.strip()
        if not raw: continue
        m = re.match(r"^(?:[-*]\s*)?([A-Za-z][A-Za-z /&+.-]{1,32}):\s*(.+)$", raw.lstrip("\x01\x02"))
        lay = re.match(r"^\x01(.+?)\s{2,}(.+)$", raw)
        if lay: groups.append({"label": plain(lay.group(1)).strip(": "), "items": _items(lay.group(2)), "_cont": not raw.rstrip().endswith(",")})
        elif m: groups.append({"label": m.group(1).strip(), "items": _items(m.group(2))})
        elif groups and not raw.startswith("\x01"):                                              # wrapped continuation of the previous row
            it = _items(raw)
            if groups[-1].get("_cont") and it: groups[-1]["items"][-1] += " " + it.pop(0)         # 'prompt' / 'engineering' was one item
            groups[-1]["items"] += it; groups[-1]["_cont"] = not raw.rstrip().endswith(",")
            continue
        elif raw.startswith("\x01"): groups.append({"label": "", "items": _items(raw.lstrip("\x01"))})
    # a continuation line split a multi-word item ('prompt' / 'engineering'): re-join when the previous row ended without a comma
    for g in groups: g.pop("_cont", None)
    return groups
def _items(t: str) -> list[str]:
    return [x.strip(" .") for x in re.split(r"[,;|•]+", t) if x.strip(" .")]

def split_sections(text: str):
    """text -> (sections{key: lines}, order[keys as seen], titles{key: original heading}, extras[(title, lines)], header_lines)"""
    lines = [l.rstrip() for l in (text or "").split("\n")]
    sec, order, titles, extras = {}, [], {}, []
    cur, buf = "header", []
    def flush():
        if cur.startswith("x:"): extras.append((cur[2:], buf))
        else: sec[cur] = sec.get(cur, []) + buf
    for l in lines:
        core = l.strip().lstrip("\x01\x02").strip()
        hit = next((k for k, r in HEAD_RE.items() if r.match(core)), None)
        unknown = (not hit) and l.lstrip().startswith("\x02")
        if hit or unknown:
            flush(); cur = hit or "x:" + core.strip(": "); buf = []
            if hit and hit not in order: order.append(hit); titles[hit] = core.strip(": ")
            if unknown: order.append(cur); titles[cur] = core.strip(": ")
        else: buf.append(l)
    flush()
    return sec, order, titles, extras

_PHONE = re.compile(r"\+?\(?\d[\d ()\-]{7,}\d")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
def parse_header(lines: list[str], name: str = "") -> dict:
    """Lines above the first section -> {name, tagline[], contact[], note}. Link markup is kept."""
    hl = [x.strip().lstrip("\x01\x02").strip() for x in lines if x.strip()]
    if hl and (not name or plain(hl[0]) == name): name = name or plain(hl[0]); hl = hl[1:]
    ci = next((i for i, l in enumerate(hl) if _EMAIL.search(l) or _PHONE.search(plain(l))), None)
    if ci is None: return {"name": name, "tagline": hl[:3], "contact": [], "note": ""}
    tag = hl[:ci]; contact = [hl[ci]]; rest = hl[ci + 1:]
    while rest and len(rest[0]) <= 220 and (LINK_RE.search(rest[0]) or "•" in rest[0] or "|" in rest[0]) and not re.search(r"[a-z]\.\s+[A-Z]", plain(rest[0])): contact.append(rest.pop(0))
    return {"name": name, "tagline": tag, "contact": contact, "note": " ".join(rest).replace("** **", " ")}

def build_cv(sec, order, titles, extras, flat, header_name="", footer=""):
    head = parse_header(sec.get("header", []), header_name) if sec.get("header") else None
    hflat = "\n".join(head["contact"]) if head and head["contact"] else flat
    email = (_EMAIL.search(LINK_RE.sub(r"\1", hflat)) or [None])[0] or (_EMAIL.search(flat) or [None])[0]
    phone = next((m for m in _PHONE.findall(plain(hflat)) if 9 <= len(re.sub(r"\D", "", m)) <= 15 and not DATE_RE.search(m)), None)
    urls = [u for _, u in LINK_RE.findall("\n".join(head["contact"]))] if head else []
    links = list(dict.fromkeys(urls + re.findall(r"(?:https?://)?(?:www\.)?(?:linkedin\.com/in/[\w\-%]+|github\.com/[\w\-]+|gitlab\.com/[\w\-]+)", flat, re.I)))
    city = ""
    if head and head["contact"]:                                           # first plain item of the contact line ('Bologna, Italy')
        for it in re.split(r"\s*[•|·]\s*", plain(head["contact"][0])):
            if it and not _EMAIL.search(it) and not _PHONE.search(it) and not re.search(r"https?://|www\.|\.\w{2,3}$|:", it): city = it; break
    if not city:
        low = (head and plain(" ".join(head["contact"])).lower()) or flat.lower()[:800]
        city = next((c.title() for c in sorted(nl.CITIES, key=len, reverse=True) if c and re.search(rf"(?<!\w){re.escape(c)}(?!\w)", low)), "")
    name = header_name or (head["name"] if head else "")
    if not name:
        for l in flat.split("\n")[:8]:
            s = plain(l.strip().lstrip("\x01\x02"))
            if 2 <= len(s.split()) <= 4 and not re.search(r"[\d@:/|]", s) and s.replace(" ", "").replace("-", "").replace("'", "").replace(".", "").isalpha() and not any(r.match(s) for r in HEAD_RE.values()):
                name = s; break
    summary = " ".join(x.strip().lstrip("\x01\x02") for x in sec.get("summary", []) if x.strip()).replace("** **", " ")[:1500]
    groups = _skill_groups(sec.get("skills", []))
    if groups: listed = [i for g in groups for i in g["items"]]
    else:
        skills_txt = "\n".join(x.lstrip("\x01\x02") for x in sec.get("skills", []))
        listed = [re.sub(r"^[-*]\s*", "", t).strip(" .") for t in re.split(r"[,;|\n•]+|\s{3,}", re.sub(r"^[A-Za-z /&]{3,30}:\s*", "", skills_txt, flags=re.M)) if t.strip()]
    listed = [t for t in listed if 1 < len(t) <= 40]
    detected = find_terms(flat)
    skills = list(dict.fromkeys(listed + [pretty(t) for t in detected if t not in {x.lower() for x in listed}]))[:80]
    return {
        "name": name, "email": email or "", "phone": (phone or "").strip(), "location": city, "links": links, "header": head, "footer": footer,
        "summary": summary, "skills": skills, "skill_groups": groups,
        "experience": _blocks(sec.get("experience", [])), "education": _blocks(sec.get("education", [])),
        "projects": _blocks(sec.get("projects", [])),
        "languages": parse_languages(sec.get("languages", [])),
        "references": extract_references(sec.get("languages", []) + sec.get("other", [])),
        "certifications": [s.strip(" -").lstrip("\x01\x02") for s in sec.get("certifications", []) if s.strip(" -")][:10],
        "extras": [{"title": t, "blocks": _blocks(ls)} for t, ls in extras],
        "order": order, "titles": titles,
        "warnings": ([] if name else ["Could not detect your name — please fill it in."]) + ([] if sec.get("experience") or sec.get("projects") or extras else ["No Experience/Projects section found — check the headings or edit manually."]),
    }

def parse_cv(text: str, footer: str = "") -> dict:
    text = "\n".join(strip_footer(l) if _FOOTER_RE.search(l) else l for l in (text or "").split("\n"))
    sec, order, titles, extras = split_sections(text)
    return build_cv(sec, order, titles, extras, text or "", footer=footer)

# ---------------------------------------------------------------- tailoring
def job_keywords(job: dict) -> list[str]:
    """Requirement terms of a job: vocabulary hits weighted toward the title and the first part of the description."""
    title, desc = job.get("title", ""), job.get("description", "") or ""
    scored = {}
    for t in find_terms(title): scored[t] = scored.get(t, 0) + 5
    for t in find_terms(desc[:6000]): scored[t] = scored.get(t, 0) + 1 + desc.lower().count(t) * 0.3
    return [t for t, _ in sorted(scored.items(), key=lambda x: -x[1])][:25]

def _overlap(text: str, kws: set[str]) -> int:
    return len(kws & set(find_terms(text)))

def tailor(cv: dict, job: dict, company: str = "") -> dict:
    kws = job_keywords(job); kset = set(kws)
    cv_skills = [s for s in cv.get("skills", []) if s]
    cv_low = {s.lower(): s for s in cv_skills}
    cv_text = " ".join([cv.get("summary", "")] + cv_skills + [b["heading"] + " " + b.get("desc", "") + " " + b.get("tech", "") + " " + " ".join(b["bullets"]) for k in ("experience", "projects", "education") for b in cv.get(k, [])] + [b["heading"] + " " + b.get("desc", "") + " " + b.get("tech", "") for e in cv.get("extras", []) for b in e["blocks"]])
    cv_terms = set(find_terms(cv_text)) | set(cv_low)
    matched = [k for k in kws if k in cv_terms]
    gaps = [k for k in kws if k not in cv_terms]
    skills = sorted(cv_skills, key=lambda s: (0 if s.lower() in kset or any(s.lower() in k or k in s.lower() for k in matched if len(k) > 2) else 1))
    def rank(blocks, maxb):
        out = []
        for b in blocks:
            bl = sorted(b["bullets"], key=lambda x: -_overlap(x, kset))[:maxb]
            out.append({**b, "bullets": bl, "score": _overlap(b["heading"] + " " + b.get("desc", "") + " " + b.get("tech", "") + " " + " ".join(b["bullets"]), kset)})
        return sorted(out, key=lambda b: -b["score"]) if len(out) > 1 and any(b["score"] for b in out) else out
    intern = job.get("job_type") in ("internship", "traineeship")
    exp = rank(cv.get("experience", []), 5); proj = rank(cv.get("projects", []), 4)
    jt = job.get("title", "this role")
    top = [s for s in skills if s.lower() in matched or s.lower() in kset][:5] or skills[:4]
    base = (cv.get("summary") or "").strip()
    focus = f"Targeting {jt}" + (f" at {company}" if company else "") + (f" — strongest in {', '.join(top)}." if top else ".")
    summary = (focus + (" " + base if base else "")).strip()
    score = round(100 * len(matched) / max(1, len(kws))) if kws else 0
    order = ["education", "projects", "experience"] if intern else ["experience", "projects", "education"]
    t = {"name": cv.get("name", ""), "email": cv.get("email", ""), "phone": cv.get("phone", ""), "location": cv.get("location", ""), "links": cv.get("links", []),
         "summary": summary, "skills": skills, "experience": exp, "projects": proj, "education": cv.get("education", []),
         "languages": cv.get("languages", []), "certifications": cv.get("certifications", []), "order": order,
         **{k: cv[k] for k in ("extras", "titles", "references", "skill_groups", "header", "footer") if k in cv}}
    return {"cv": t, "keywords": kws, "matched": matched, "gaps": gaps, "match_score": score, "target": {"title": jt, "company": company}}

# ---------------------------------------------------------------- rendering
def _e(s): return _html.escape(str(s or ""))

def render_text(t: dict) -> str:
    L = [t["name"].upper(), " | ".join(x for x in [t["email"], t["phone"], t["location"], *t["links"]] if x), ""]
    if t["summary"]: L += ["SUMMARY", t["summary"], ""]
    if t["skills"]: L += ["SKILLS", ", ".join(t["skills"]), ""]
    for sec in t["order"]:
        items = t.get(sec) or []
        if not items: continue
        L.append(sec.upper())
        for b in items:
            L.append(b["heading"]); L += [f"- {x}" for x in b["bullets"]]; L.append("")
    if t["languages"]: L += ["LANGUAGES", ", ".join(t["languages"]), ""]
    if t["certifications"]: L += ["CERTIFICATIONS"] + [f"- {c}" for c in t["certifications"]]
    return "\n".join(L).strip() + "\n"

def render_html(t: dict) -> str:
    """Single-column, ATS-friendly, print-to-PDF ready."""
    def sec(title, body): return f"<h2>{title}</h2>{body}" if body else ""
    def blocks(items): return "".join(f"<div class='b'><b>{_e(b['heading'])}</b><ul>{''.join(f'<li>{_e(x)}</li>' for x in b['bullets'])}</ul></div>" for b in items)
    contact = " · ".join(_e(x) for x in [t["email"], t["phone"], t["location"], *t["links"]] if x)
    parts = {"experience": sec("Experience", blocks(t.get("experience", []))), "projects": sec("Projects", blocks(t.get("projects", []))), "education": sec("Education", blocks(t.get("education", [])))}
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{_e(t['name'])} — CV</title><style>
body{{font:11pt/1.4 -apple-system,Segoe UI,Helvetica,Arial,sans-serif;color:#111;max-width:780px;margin:32px auto;padding:0 24px}}
h1{{margin:0;font-size:22pt}} .c{{color:#444;margin:4px 0 14px}} h2{{font-size:11pt;letter-spacing:.08em;text-transform:uppercase;border-bottom:1px solid #999;margin:16px 0 6px;padding-bottom:2px}}
ul{{margin:3px 0 8px 18px;padding:0}} li{{margin:1px 0}} .b{{break-inside:avoid}} @media print{{body{{margin:0}}}}</style></head><body>
<h1>{_e(t['name'])}</h1><div class="c">{contact}</div>
{sec('Summary', f"<p>{_e(t['summary'])}</p>" if t['summary'] else '')}{sec('Skills', f"<p>{_e(', '.join(t['skills']))}</p>" if t['skills'] else '')}
{''.join(parts[k] for k in t['order'])}
{sec('Languages', f"<p>{_e(', '.join(t['languages']))}</p>" if t['languages'] else '')}{sec('Certifications', ('<ul>' + ''.join(f'<li>{_e(c)}</li>' for c in t['certifications']) + '</ul>') if t['certifications'] else '')}
</body></html>"""

# ---------------------------------------------------------------- cover letter
def _first_sentence(s, n=200):
    s = re.sub(r"\s+", " ", s or "").strip()
    m = re.match(r"(.{30,%d}?[.!?])(\s|$)" % n, s)
    return m.group(1) if m else (s[:n].rsplit(" ", 1)[0] + "…" if len(s) > n else s)

def _clean_heading(h: str) -> str:
    h = DATE_RE.sub("", h or "")
    h = re.sub(r"\s{2,}.*$", "", h)                      # trailing columns
    return re.sub(r"\s*[|,\-–—]\s*$", "", h.split("|")[0]).strip(" -–—|,")
_VERB = re.compile(r"^(built|wrote|led|ran|made|developed|designed|implemented|created|launched|improved|reduced|increased|managed|delivered|optimi[sz]ed|migrated|automated|integrated|tested|deployed|maintained|collaborated|analy[sz]ed|conducted|organi[sz]ed|\w+ed)\b", re.I)
def _evidence(heading: str, bullet: str, is_project: bool) -> str:
    b = bullet.strip().rstrip(".")
    if _VERB.match(b): return f"In my role as {heading}, I {b[0].lower() + b[1:]}." if not is_project else f"In my project {heading}, I {b[0].lower() + b[1:]}."
    return (f"In my project {heading}: {b}." if is_project else f"In my role as {heading}: {b}.")

def cover_letter(cv: dict, job: dict, company: dict | None = None, tone: str = "professional", extra: str = "") -> dict:
    """Template letter built only from the CV's own facts + the posting. Bracketed [..] parts are for the user to complete."""
    company = company or {}
    tl = tailor(cv, job, company.get("name", ""))
    t, matched = tl["cv"], tl["matched"]
    cname = company.get("name") or "your company"
    role = job.get("title", "this position")
    intern = job.get("job_type") in ("internship", "traineeship")
    sk = [s for s in t["skills"] if s.lower() in {m.lower() for m in matched}][:4] or t["skills"][:3]
    ev = []
    for is_p, blocks in ((False, t["experience"]), (True, t["projects"])):
        for b in blocks:
            for x in b["bullets"][:1]:
                if _overlap(x, set(tl["keywords"])) and _clean_heading(b["heading"]): ev.append(_evidence(_clean_heading(b["heading"]), x, is_p))
    ev = ev[:2]
    why = _first_sentence(company.get("description", "")) if len((company.get("description") or "").split()) >= 6 else ""
    greet = "Dear Hiring Team," if tone != "casual" else "Hi team,"
    p1 = f"I am writing to apply for the {role} {'internship ' if intern and 'intern' not in role.lower() else ''}position at {cname}."
    if why: p1 += f" {cname} caught my attention: {why}"
    else: p1 += f" I am excited about the opportunity to contribute to {cname} and its work in the Netherlands."
    edu = _clean_heading(t["education"][0]["heading"]) if t["education"] else ""
    p2 = (f"Currently {('studying ' + edu) if edu else 'building my experience'}, " if intern and edu else "") + \
         (f"my background is strongest in {', '.join(sk[:-1]) + (' and ' if len(sk) > 1 else '') + sk[-1]}, which the role calls for." if sk else "I bring a solid technical foundation that matches the role.")
    p2 = p2[0].upper() + p2[1:]
    if ev: p2 += " " + " ".join(ev)
    gaps = [g for g in tl["gaps"] if g in set(find_terms(job.get("title", "")))][:2]
    p3 = f"I am also keen to deepen my skills in {' and '.join(gaps)}." if gaps else ""
    p4 = (extra.strip() + " ") if extra.strip() else "[Add one sentence on why this team or product motivates you.] "
    p4 += "I would welcome the chance to discuss how I can contribute" + (" and learn alongside your team." if intern else ".") + (" I am based in " + t["location"] + "." if t["location"] else "")
    body = "\n\n".join(x for x in [greet, p1, p2, p3, p4.strip(), f"Kind regards,\n{t['name']}\n{t['email']} {t['phone']}".rstrip()] if x)
    return {"text": body, "matched": matched, "gaps": tl["gaps"], "placeholders": body.count("[")}

# ---------------------------------------------------------------- optional LLM polish (off by default)
def polish(kind: str, cv_text: str, job: dict, draft: str, api_key: str) -> str:
    import httpx
    sys_p = ("You edit job-application documents. Use ONLY facts present in the candidate's CV text. Never invent employers, dates, degrees, skills, numbers or "
             "motivations. Keep it concise, specific to the posting, and natural. If something is missing, leave a [bracketed placeholder].")
    msg = f"Improve this {kind} for the posting below. Return only the improved text.\n\nPOSTING: {job.get('title','')} — {(job.get('description') or '')[:3500]}\n\nCV:\n{cv_text[:6000]}\n\nDRAFT:\n{draft}"
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=60,
                   headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json={"model": "claude-sonnet-5-5", "max_tokens": 1800, "system": sys_p, "messages": [{"role": "user", "content": msg}]})
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json().get("content", [])) or draft

# ---------------------------------------------------------------- import pipeline (PDF / DOCX / text / LaTeX -> structured CV + LaTeX source)
def looks_like_latex(text: str) -> bool: return bool(re.search(r"\\documentclass|\\begin\{document\}|\\section\*?\{", text or ""))

def import_cv(data: bytes, filename: str = "") -> dict:
    """-> {cv, latex, text, source}. PDFs are read layout-aware and converted to LaTeX; LaTeX uploads are parsed as-is and kept verbatim."""
    from . import latexcv, pdflayout
    if len(data) > MAX_BYTES: raise ValueError("file too large (max 3 MB)")
    name = (filename or "").lower()
    if data[:4] == b"%PDF" or name.endswith(".pdf"):
        text, footer = "", ""
        try: d = pdflayout.pdf_to_doc(data); text, footer = d["text"], d["footer"]
        except Exception: text = ""
        if len(text) < 60: text = extract_text(data, filename)          # fall back to plain text extraction
        source = "pdf"
    elif data[:2] == b"PK" or name.endswith(".docx"):
        footer = ""
        text, source = extract_text(data, filename), "docx"
    else:
        footer = ""
        text, source = data.decode("utf8", "ignore"), "text"
        if name.endswith(".tex") or looks_like_latex(text):
            if not latexcv.is_safe(text): raise ValueError("LaTeX contains disallowed commands (\\input, \\write, \\catcode, …)")
            cvd = latexcv.parse_latex(text)
            return {"cv": cvd, "latex": text, "text": latexcv.to_text(text)[:30000], "source": "latex"}
    if len(text) < 40: raise ValueError("no readable text found (scanned image PDF? paste the text instead)")
    cvd = parse_cv(text, footer if source == "pdf" else "")
    return {"cv": cvd, "latex": latexcv.to_latex(cvd), "text": text[:30000], "source": source}


# ---------------------------------------------------------------- AI tailoring (opt-in: the CV and the posting are sent to Anthropic)
_AI_SYS = ("You tailor a candidate's CV to one job posting. HARD RULES: use ONLY facts already in the CV; never invent employers, dates, degrees, skills, tools, numbers or achievements; "
           "do not add a skill the CV does not mention (list such requirements under 'gaps'). You may reword for clarity and for the posting's vocabulary, reorder, merge or shorten. "
           "Keep every [label](url) link and **bold** marker exactly as written. Keep the candidate's language and a concise, factual tone. "
           "Reply with ONLY a JSON object: {\"summary\": str, \"sections\": {\"<section id>\": [{\"i\": int, \"desc\": str|null, \"bullets\": [str]|null}]}, "
           "\"skills_first\": [str], \"gaps\": [str], \"notes\": str}. Only include entries you changed; \"i\" is the entry index shown in the input.")

def _ai_input(cv: dict) -> tuple[str, dict]:
    """CV -> compact numbered text for the model, plus {section id: blocks} so the answer can be applied back."""
    secs = {"experience": cv.get("experience") or [], "projects": cv.get("projects") or [], "education": cv.get("education") or []}
    for e in cv.get("extras") or []: secs["x:" + e["title"]] = e["blocks"]
    lines = [f"SUMMARY: {cv.get('summary', '')}", "SKILLS: " + ", ".join(cv.get("skills") or [])]
    for sid, blocks in secs.items():
        if not blocks: continue
        lines.append(f"\n[section id: {sid}]")
        for i, b in enumerate(blocks):
            lines.append(f"({i}) {plain(b.get('title', '') or b.get('heading', ''))} | {plain(b.get('place', ''))} {b.get('date', '')}".rstrip())
            if b.get("desc"): lines.append(f"    desc: {b['desc']}")
            for x in b.get("bullets", []): lines.append(f"    - {x}")
    return "\n".join(lines), secs

def ai_tailor(cv: dict, job: dict, api_key: str, model: str = "claude-sonnet-5-5") -> dict:
    """-> {cv: tailored copy, changes: [{section, title, before, after}], gaps, notes}. Only summary, bullets, descriptions and skill order can change."""
    import copy, json, httpx
    text, secs = _ai_input(cv)
    posting = f"{job.get('title', '')} at {job.get('company', '')}\n{(job.get('description') or '')[:6000]}"
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=90,
                   headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                   json={"model": model, "max_tokens": 4000, "system": _AI_SYS, "messages": [{"role": "user", "content": f"JOB POSTING:\n{posting}\n\nCV:\n{text}"}]})
    r.raise_for_status()
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    if not m: raise ValueError("the model did not return JSON")
    out = json.loads(m.group(0))
    new = copy.deepcopy(cv); changes = []
    if isinstance(out.get("summary"), str) and out["summary"].strip() and out["summary"].strip() != (cv.get("summary") or "").strip():
        changes.append({"section": "Summary", "title": "", "before": cv.get("summary", ""), "after": out["summary"].strip()}); new["summary"] = out["summary"].strip()
    nsecs = {"experience": new.get("experience") or [], "projects": new.get("projects") or [], "education": new.get("education") or []}
    for e in new.get("extras") or []: nsecs["x:" + e["title"]] = e["blocks"]
    for sid, edits in (out.get("sections") or {}).items():
        blocks = nsecs.get(sid)
        if not blocks or not isinstance(edits, list): continue
        for ed in edits:
            try: i = int(ed.get("i"))
            except Exception: continue
            if not 0 <= i < len(blocks): continue
            b = blocks[i]; before = " / ".join(x for x in [b.get("desc", "")] + list(b.get("bullets", [])) if x)
            if isinstance(ed.get("desc"), str) and ed["desc"].strip(): b["desc"] = ed["desc"].strip()
            if isinstance(ed.get("bullets"), list) and ed["bullets"] and len(ed["bullets"]) <= max(len(b.get("bullets", [])), 1) + 1: b["bullets"] = [str(x).strip() for x in ed["bullets"] if str(x).strip()]
            after = " / ".join(x for x in [b.get("desc", "")] + list(b.get("bullets", [])) if x)
            if after != before: changes.append({"section": sid.replace("x:", ""), "title": plain(b.get("title", "")), "before": before, "after": after})
    first = [str(x) for x in (out.get("skills_first") or []) if str(x) in (cv.get("skills") or [])]      # only skills the CV already lists
    if first:
        rank = {x: i for i, x in enumerate(first)}
        new["skills"] = sorted(cv.get("skills") or [], key=lambda x: rank.get(x, 999))
        for g in new.get("skill_groups") or []: g["items"] = sorted(g["items"], key=lambda x: rank.get(x, 999))
    return {"cv": new, "changes": changes, "gaps": [str(x) for x in (out.get("gaps") or [])][:12], "notes": str(out.get("notes") or "")[:400]}
