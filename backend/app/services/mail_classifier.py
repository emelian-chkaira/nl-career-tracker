"""Find job-search e-mails, classify them, extract company/role/dates, and link them to the user's pipeline.

Two classifiers share one output shape:
  rules  keyword patterns (EN/NL/DE) - free, offline
  LLM    any provider from llm_service - better at company/role/dates; falls back to the rules when the model fails"""
import re, datetime as dt
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from app.models import MailEvent, Company, Job, UserJob
from . import llm_service as llm

CATEGORIES = ("application_received", "interview_invite", "assessment", "offer", "rejection", "recruiter_outreach")
STAGE_OF = {"application_received": "applied", "assessment": "screening", "interview_invite": "interview", "offer": "offer", "rejection": "rejected"}

_R = lambda p: re.compile(p, re.I)
RULES = [   # order matters: rejections and offers are checked before the generic "application" wording
    ("rejection", _R(r"unfortunately|regret to (inform|tell)|not (be )?moving forward|will not be (moving|proceeding)|other candidates|not selected|decided not to|no longer (considering|being considered)|position has been filled|helaas|met spijt|geen vervolg|andere kandidaat|leider|bedauern|absage|nicht berücksichtigen|anderen bewerber")),
    ("offer", _R(r"pleased to offer|job offer|offer letter|we('d| would) like to offer you|happy to offer|contract (is )?attached|aanbod|arbeidsovereenkomst|vacature.*aanbieden|freuen uns,? ihnen.*angebot|stellenangebot")),
    ("assessment", _R(r"assessment|coding (challenge|test|exercise)|take[- ]home|technical test|case study|hackerrank|codility|testgrid|opdracht|aufgabe|online test")),
    ("interview_invite", _R(r"interview|invite you to (a|an) (call|chat|meeting)|schedule (a|an) (call|chat|conversation)|next step|calendly|select a time|gesprek|uitnodiging|kennismaking|vorstellungsgespräch|termin")),
    ("application_received", _R(r"thank you for (your )?appl|we (have )?received your application|application (received|submitted|confirmation)|your application (to|for|at)|bedankt voor je sollicitatie|sollicitatie ontvangen|vielen dank für ihre bewerbung|bewerbung eingegangen")),
    ("recruiter_outreach", _R(r"came across your (profile|cv|resume)|your (linkedin )?profile|exciting opportunity|i('m| am) a (technical )?recruiter|reaching out (about|regarding)|open (role|position) (that|which)|zag je profiel|ben je open voor")),
]
JOBISH = _R(r"applic|interview|position|vacanc|vacature|sollicit|recruit|candidate|kandidaat|career|hiring|offer|role\b|bewerbung|stelle|assess|challenge|assignment|take-?home|opdracht|aufgabe|opportunit|your profile|your cv|your resume|jobs?\b")
NOISE_SENDER = _R(r"(no-?reply@)?(newsletter|digest|marketing|promo|deals|noreply@(medium|linkedin|facebook|twitter|instagram|pinterest|quora)\.)")
ROLE_RES = [_R(r"(?:for|as|applying to|applied (?:for|to)|regarding|about)(?: the| our| a| an)? ['\"“]?((?-i:[A-Z])[\w&/.,+\- ]{3,70}?)['\"”]? (?:position|role|vacancy|opening|job|vacature|functie|stelle)"),
            _R(r"(?:position|role|vacature|functie|stelle)[:\-–] ['\"“]?((?-i:[A-Z])[\w&/.,+\- ]{3,70})")]


def _company_from(sender: str, subject: str) -> str | None:
    m = re.search(r"\b(?:at|bij|@|from|with)\s+([A-Z][\w&.\- ]{1,40}?)(?:[,.!:\-–]|\s+(?:for|as|is|has|we|the)\b|$)", subject or "")
    if m: return m.group(1).strip()
    name = (re.match(r"\s*\"?([^<\"]+?)\"?\s*<", sender or "") or [None, ""])[1].strip()
    name = re.sub(r"\b(recruiting|recruitment|talent|careers?|jobs?|hr|hiring|team|no-?reply|notifications?)\b", "", name, flags=re.I).strip(" -–|,")
    if name and "@" not in name and len(name) > 1: return name[:80]
    dom = re.search(r"@([\w.-]+)", sender or "")
    if dom:
        parts = dom.group(1).lower().split(".")
        base = parts[-3] if len(parts) >= 3 and parts[-2] in ("co", "com", "org") else (parts[-2] if len(parts) >= 2 else "")
        if base in ("greenhouse", "lever", "workday", "smartrecruiters", "myworkday", "ashbyhq", "gmail", "outlook", "hotmail", "yahoo", "icloud") and len(parts) >= 3: base = parts[-3]
        if base and base not in ("gmail", "outlook", "hotmail", "yahoo", "icloud", "greenhouse", "lever"): return base.capitalize()
    return None


def looks_job_related(mail: dict) -> bool:
    hay = f"{mail.get('subject','')} {mail.get('body','')[:1500]}"
    return bool(JOBISH.search(hay)) and not NOISE_SENDER.search(mail.get("sender_addr", "") or "")


def classify_rules(mail: dict) -> dict | None:
    subject, body = mail.get("subject", ""), mail.get("body", "")
    hay = f"{subject}\n{body[:2500]}"
    for cat, rx in RULES:
        m = rx.search(subject) or rx.search(hay)
        if not m: continue
        role = next((x.group(1).strip(" .,") for r in ROLE_RES for x in [r.search(hay)] if x), None)
        conf = 0.8 if rx.search(subject) else 0.6
        return dict(category=cat, company=_company_from(mail.get("sender", ""), subject), role=role, location=None, event_date=None,
                    summary=(re.sub(r"\s+", " ", body)[:200] or subject)[:300], confidence=conf, classifier="rules")
    return None


SYSTEM = """You read one e-mail from a person's inbox and decide whether it is part of THEIR job search.
Answer with ONE JSON object and nothing else:
{"category": one of ["application_received","interview_invite","assessment","offer","rejection","recruiter_outreach","not_job_related"],
 "company": string or null, "role": string or null, "location": string or null,
 "event_date": interview/deadline date-time as written or ISO, or null,
 "summary": one short sentence (max 160 chars), "confidence": number 0..1}
Rules: rejection = they will not continue with the candidate. offer = a job offer or contract. interview_invite = asks to schedule or confirms an interview/call.
assessment = a test, coding challenge or take-home. application_received = automatic confirmation of an application. recruiter_outreach = someone approaches the candidate.
Newsletters, job-alert digests, marketing and anything not about the candidate's own applications are not_job_related. Never invent facts: use null when unknown."""


def classify_llm(cfg: llm.Cfg, mail: dict) -> dict | None:
    user = f"From: {mail.get('sender','')}\nSubject: {mail.get('subject','')}\nDate: {mail.get('date')}\n\n{mail.get('body','')[:3500]}"
    d = llm.parse_json(llm.complete(cfg, SYSTEM, user, max_tokens=400))
    cat = str(d.get("category", "")).strip()
    if cat not in CATEGORIES: return None
    s = lambda k, n: (str(d[k]).strip()[:n] or None) if d.get(k) not in (None, "", "null") else None
    try: conf = max(0.0, min(1.0, float(d.get("confidence", 0.7))))
    except (TypeError, ValueError): conf = 0.7
    return dict(category=cat, company=s("company", 200), role=s("role", 250), location=s("location", 200), event_date=s("event_date", 80), summary=s("summary", 300), confidence=conf, classifier=cfg.label)


def classify(cfg: llm.Cfg, mail: dict) -> tuple[dict | None, str | None]:
    """-> (result or None when it is not a job e-mail, warning). The LLM decides when configured; the rules are the fallback if it fails."""
    if cfg.kind != "rules":
        try: return classify_llm(cfg, mail), None
        except llm.LlmError as e: warn = f"AI failed ({e}); used the built-in rules"
    else: warn = None
    return classify_rules(mail), warn


def _norm(s: str | None) -> str: return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def link(db: Session, user_id, res: dict, sender_addr: str = "") -> tuple[int | None, int | None]:
    """Find the company (by name, then by the sender's domain) and the user's pipeline job at that company (best title overlap)."""
    cid = None
    n = _norm(res.get("company"))
    if n and len(n) >= 3:
        rows = db.execute(text("SELECT id, name FROM companies")).all() if False else db.execute(select(Company.id, Company.name).where(Company.name.ilike(f"%{res['company'][:40]}%")).limit(25)).all()
        best = sorted(rows, key=lambda r: (_norm(r[1]) != n, abs(len(_norm(r[1])) - len(n))))
        if best: cid = best[0][0]
    if not cid and sender_addr and "@" in sender_addr:
        dom = sender_addr.split("@")[1].split(".")[-2] if sender_addr.count(".") else ""
        if len(dom) >= 4:
            r = db.scalar(select(Company.id).where(Company.website.ilike(f"%{dom}%")).limit(1))
            cid = r or cid
    if not cid: return None, None
    jobs = db.execute(select(Job.id, Job.title).join(UserJob, UserJob.job_id == Job.id).where(UserJob.user_id == user_id, Job.company_id == cid)).all()
    if not jobs: return cid, None
    want = set(re.findall(r"[a-z0-9+#]{3,}", (res.get("role") or "").lower()))
    if want:
        best = max(jobs, key=lambda j: len(want & set(re.findall(r"[a-z0-9+#]{3,}", j[1].lower()))))
        if want & set(re.findall(r"[a-z0-9+#]{3,}", best[1].lower())): return cid, best[0]
    return cid, (jobs[0][0] if len(jobs) == 1 else None)


def process(db: Session, user_id, cfg: llm.Cfg, mails: list[dict], account_id: int | None = None, progress=None) -> dict:
    """Classify messages and store the extracted facts as MailEvents (new ones only). Returns counters."""
    stats = dict(scanned=0, skipped=0, found=0, duplicate=0, ai_failed=0, unclassified=0)
    known = {r[0] for r in db.execute(select(MailEvent.message_id).where(MailEvent.user_id == user_id))}
    for i, m in enumerate(mails):
        stats["scanned"] += 1
        if m["message_id"] in known: stats["duplicate"] += 1; continue
        if not looks_job_related(m): stats["skipped"] += 1; continue
        res, warn = classify(cfg, m)
        if warn: stats["ai_failed"] += 1
        if not res: stats["skipped"] += 1; stats["unclassified"] += 1; continue
        cid, jid = link(db, user_id, res, m.get("sender_addr", ""))
        db.add(MailEvent(user_id=user_id, account_id=account_id, message_id=m["message_id"], sender=m.get("sender"), subject=m.get("subject"), received_at=m.get("date"),
                         company_id=cid, job_id=jid, **res)); known.add(m["message_id"]); stats["found"] += 1
        if stats["found"] % 10 == 0: db.commit()
        if progress and i % 5 == 0: progress(**stats)
    db.commit(); return stats


def apply_stage(db: Session, user_id, ev: MailEvent, job_id: int | None = None) -> str | None:
    """Move the linked job in the user's pipeline according to the e-mail. Rejections/offers/interviews are never silently downgraded."""
    jid = job_id or ev.job_id; stage = STAGE_OF.get(ev.category)
    if not jid or not stage: return None
    uj = db.get(UserJob, (user_id, jid)) or UserJob(user_id=user_id, job_id=jid, stage=stage)
    order = ["shortlisted", "applied", "screening", "interview", "offer"]
    if uj.stage in order and stage in order and order.index(uj.stage) > order.index(stage): return uj.stage            # keep the further stage
    uj.stage = stage; db.add(uj); return stage
