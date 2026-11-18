"""Intelligent job search: concept expansion (flutter -> dart, mobile, ios, android, cross-platform...), weighted ranking
(title > description), phrase + fuzzy matching, and an explanation of why each job matched. No keyword-AND strictness: OR with coverage scoring."""
import re, difflib

# concept clusters: key -> (aliases that mean the same, related terms that mean "close")
ONTOLOGY = {
    "flutter": (["flutter", "dart"], ["mobile", "cross-platform", "cross platform", "ios", "android", "app developer", "react native", "kotlin multiplatform", "swift", "kotlin", "mobile engineer", "mobile developer"]),
    "mobile": (["mobile", "ios", "android", "app developer", "flutter", "react native"], ["swift", "swiftui", "kotlin", "jetpack compose", "xamarin", "cross-platform", "dart", "objective-c"]),
    "react native": (["react native"], ["mobile", "ios", "android", "flutter", "cross-platform", "javascript"]),
    "ios": (["ios", "swift", "swiftui", "objective-c"], ["mobile", "apple", "flutter", "react native"]),
    "android": (["android", "kotlin", "jetpack compose"], ["mobile", "flutter", "react native", "java"]),
    "react": (["react", "reactjs", "react.js"], ["frontend", "front-end", "javascript", "typescript", "next.js", "nextjs", "web developer", "ui engineer"]),
    "frontend": (["frontend", "front-end", "front end", "ui engineer"], ["react", "vue", "angular", "javascript", "typescript", "web developer", "css"]),
    "backend": (["backend", "back-end", "back end", "server-side"], ["api", "python", "java", "node", "go", "golang", "microservices", "django", "spring", ".net", "ruby", "php"]),
    "fullstack": (["fullstack", "full-stack", "full stack"], ["frontend", "backend", "web developer", "javascript", "react", "node"]),
    "python": (["python"], ["django", "flask", "fastapi", "backend", "data engineer", "machine learning", "pandas"]),
    "java": (["java", "jvm"], ["spring", "kotlin", "backend", "scala"]),
    "javascript": (["javascript", "js", "typescript", "ts"], ["node", "react", "vue", "angular", "frontend", "web developer"]),
    "node": (["node", "nodejs", "node.js"], ["javascript", "typescript", "backend", "express"]),
    "golang": (["golang", "go developer", "go engineer"], ["backend", "microservices", "kubernetes"]),
    ".net": ([".net", "dotnet", "c#", "csharp"], ["backend", "azure", "asp.net"]),
    "data scientist": (["data scientist", "data science"], ["machine learning", "ml", "ai", "statistics", "python", "analytics", "data analyst"]),
    "machine learning": (["machine learning", "ml engineer", "ml"], ["ai", "data scientist", "deep learning", "llm", "nlp", "mlops", "computer vision"]),
    "ai": (["ai", "artificial intelligence", "llm", "genai", "generative ai"], ["machine learning", "ml", "nlp", "data scientist", "deep learning"]),
    "data engineer": (["data engineer", "data engineering", "etl"], ["spark", "airflow", "sql", "dbt", "snowflake", "bigquery", "data platform", "analytics engineer"]),
    "data analyst": (["data analyst", "bi analyst", "business intelligence"], ["sql", "tableau", "power bi", "analytics", "data scientist", "reporting"]),
    "devops": (["devops", "sre", "site reliability", "platform engineer"], ["kubernetes", "docker", "terraform", "aws", "cloud", "infrastructure", "ci/cd", "azure", "gcp"]),
    "cloud": (["cloud", "aws", "azure", "gcp"], ["devops", "infrastructure", "kubernetes", "solutions architect", "platform"]),
    "security": (["security", "cybersecurity", "infosec", "appsec"], ["penetration", "soc", "compliance", "iam", "devsecops", "risk"]),
    "qa": (["qa", "quality assurance", "test engineer", "sdet", "tester"], ["automation", "testing", "selenium", "cypress"]),
    "design": (["designer", "ux", "ui/ux", "product designer", "ux designer"], ["figma", "user research", "ui", "interaction design", "visual design"]),
    "product": (["product manager", "product owner"], ["roadmap", "stakeholder", "agile", "scrum", "product"]),
    "intern": (["intern", "internship", "stage", "stagiair", "stagiaire", "werkstudent", "working student", "stageplek", "internships", "stages"], ["trainee", "graduate", "traineeship", "junior", "entry level", "thesis", "afstudeer", "afstudeeropdracht", "meewerkstage", "graduation project", "student", "early careers", "summer internship", "research intern"]),
    "junior": (["junior", "entry level", "entry-level", "graduate"], ["trainee", "intern", "associate"]),
    "marketing": (["marketing"], ["growth", "seo", "content", "brand", "campaign", "social media"]),
    "sales": (["sales", "account executive", "sdr", "bdr"], ["business development", "account manager", "customer success"]),
    "finance": (["finance", "financial", "accountant", "controller"], ["accounting", "fp&a", "audit", "treasury", "risk"]),
    "engineer": (["engineer", "developer", "programmer", "ontwikkelaar", "software engineer"], ["software", "technical", "engineering"]),
}
GENERIC = {"developer", "engineer", "job", "jobs", "position", "role", "work", "software", "senior", "the", "a", "and", "in", "for", "of", "to", "at", "remote", "ontwikkelaar"}
SYN_TO_KEY = {}
for k, (al, rel) in ONTOLOGY.items():
    for a in al: SYN_TO_KEY.setdefault(a, k)

NOISE = re.compile(r"mobile (network|networks|operator|operators|phone|phones|home|infrastructure)|android (tv|auto)", re.I)   # "mobile" meaning telecom, not apps
def _stem(w): return re.sub(r"(ing|ers|er|s|ment)$", "", w) if len(w) > 5 else w
def parse(query):
    """-> list of concept groups: {label, strong:[terms], related:[terms], generic:bool}"""
    q = " " + re.sub(r"[^\w\s.#+/-]", " ", query.lower()) + " "
    groups, used = [], set()
    # longest-phrase first so "machine learning" / "react native" / "data scientist" stay together
    for phrase in sorted(set(list(ONTOLOGY) + list(SYN_TO_KEY)), key=len, reverse=True):
        if f" {phrase} " in q and phrase not in used:
            key = phrase if phrase in ONTOLOGY else SYN_TO_KEY[phrase]
            al, rel = ONTOLOGY[key]
            groups.append(dict(label=phrase, strong=list(dict.fromkeys([phrase] + al if phrase in al or phrase == key else [phrase] + al)), related=rel, generic=key == "engineer"))
            used.add(phrase); q = q.replace(f" {phrase} ", " ", 1)
    for w in q.split():
        if len(w) < 2 or w in used: continue
        groups.append(dict(label=w, strong=[w, _stem(w)] if _stem(w) != w else [w], related=[], generic=w in GENERIC))
    return groups

_cache: dict[str, re.Pattern] = {}
def _pat(term):
    p = _cache.get(term)
    if p is None:
        p = _cache[term] = re.compile(r"(?<![\w])" + re.escape(term) + r"(?![\w])", re.I)
    return p
def _hit(term, text): return bool(_pat(term).search(text))

def score(groups, title, company, location, desc):
    """-> (score 0..100, [explanations]) or (0, []) when nothing relevant"""
    t, c, l, d = title.lower(), company.lower(), (location or "").lower(), (desc or "").lower()[:4000]
    t, d = NOISE.sub(" ", t), NOISE.sub(" ", d)
    total = got = 0.0; why = []; specific_hit = False
    for g in groups:
        w = 0.35 if g["generic"] else 1.0
        total += w; best = 0.0; reason = None
        for term in g["strong"]:
            if _hit(term, t): best, reason = 1.0, f"title: {term}"; break
            if _hit(term, c) or _hit(term, l): best, reason = max(best, 0.8), reason or f"{'company' if _hit(term, c) else 'location'}: {term}"
            elif best < 0.55 and _hit(term, d): best, reason = 0.55, f"description: {term}"
        if best < 0.8:
            for term in g["related"]:
                if _hit(term, t): best, reason = max(best, 0.7), f"related title: {term}"; break
            else:
                n = sum(1 for term in g["related"] if _hit(term, d))
                if n and best < 0.4: best, reason = min(0.4, 0.15 + 0.08 * n), f"related skills in description ({n})"
        if best == 0 and len(g["label"]) > 4 and not g["generic"]:   # typo tolerance on title words
            m = difflib.get_close_matches(g["label"], re.findall(r"[a-z0-9+#.]{4,}", t), n=1, cutoff=0.82)
            if m: best, reason = 0.7, f"title ~ {m[0]}"
        got += w * best
        if best and not g["generic"]: specific_hit = True
        if reason: why.append(reason)
    if total == 0 or not specific_hit and any(not g["generic"] for g in groups): return 0, []
    return round(100 * got / total), why[:4]

def rank(query, rows, min_score=25):
    groups = parse(query)
    if not groups: return rows
    out = []
    for r in rows:
        s, why = score(groups, r["title"] or "", r.get("company", ""), r.get("location", ""), r.get("description", ""))
        if s >= min_score:
            r["relevance"], r["matched"] = s, why; out.append(r)
    out.sort(key=lambda r: (-r["relevance"], -(r.get("fit") or 0)))
    return out
