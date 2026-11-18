import re
NL_REQ = re.compile(r"\b(dutch (is )?required|fluent (in )?dutch|nederlands(e)? (taal )?(vereist|spreken)|vloeiend nederlands|goede beheersing van de nederlandse|native dutch)\b", re.I)
NL_PLUS = re.compile(r"\b(dutch (is )?a plus|dutch (is )?an advantage|nederlands is een pre)\b", re.I)
def language(title, desc):
    t = f"{title} {desc}"
    if NL_REQ.search(t): return "dutch_required"
    if NL_PLUS.search(t): return "dutch_plus"
    # Dutch-language posting text implies Dutch needed
    if len(re.findall(r"\b(wij|jij|je|bij|een|het|voor|met|onze)\b", (desc or "")[:1500].lower())) > 12: return "dutch_required"
    return "english_ok"
INTERN_RE = re.compile(r"\b(intern|interns|internship|internships|stage|stagiair|stagiaire|stages|werkstudent|working student|thesis|afstudeer\w*|praktikum|co-?op|apprentice\w*|summer student|student assistant|studentassistent|bijbaan|meewerkstage|praktijkopdracht|studentenbaan|student job|graduation (project|internship|assignment|thesis)|master'?s? thesis|bachelor'?s? thesis|research intern|summer (internship|school)|afstudeeropdracht|afstudeerstage|stage ?plek|stageplaats)\b", re.I)
TRAINEE_RE = re.compile(r"\b(trainee|traineeship|graduate (programme|program|scheme)|management trainee|graduate programme|young professional|starters? programma|leerwerk|early[- ]careers?|graduate (trainee|job)|starterfunctie|young talent)\b", re.I)
def job_type(title, desc=""):
    t = title or ""
    if INTERN_RE.search(t) or re.search(r"interns? and trainees?|graduate programme", desc or "", re.I): return "internship"
    if TRAINEE_RE.search(t): return "traineeship"
    low = t.lower()
    if re.search(r"junior|entry|associate\b", low): return "junior"
    if re.search(r"senior|lead|principal|staff|head of|manager|director", low): return "senior"
    return "job"
DEFAULT_PROFILE = {"skills": [], "titles": [], "cities": [], "job_types": [], "english_only": False, "salary_category": "hsm_under30"}
def fit(title, desc, location, jtype, lang, p):
    hay = f"{title} {desc}".lower()
    skills = [s.lower() for s in p.get("skills", []) if s.strip()]
    titles = [s.lower() for s in p.get("titles", []) if s.strip()]
    hit = [s for s in skills if s in hay]
    th = [s for s in titles if s in title.lower()]
    score = 0.0
    if skills: score += 55 * len(hit) / len(skills)
    if titles: score += 30 if th else 0
    else: score += 15
    cities = [c.lower() for c in p.get("cities", []) if c.strip()]
    if cities and any(c in (location or "").lower() for c in cities): score += 15
    elif not cities: score += 8
    if p.get("job_types") and jtype not in p["job_types"]: score -= 25
    if p.get("english_only") and lang == "dutch_required": score -= 40
    why = []
    if hit: why.append("skills: " + ", ".join(hit[:6]))
    if th: why.append("title match: " + th[0])
    if lang == "dutch_required": why.append("Dutch required")
    return max(0, min(100, round(score))), "; ".join(why) or "no profile signal yet"
