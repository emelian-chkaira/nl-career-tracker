"""Job domain classifier: which kind of work is this posting? Used to (a) keep only the domains you care about when storing, and (b) filter in search.

Rules look at the TITLE first (strong signal) and only then at the description/skills. First matching domain wins, so more specific domains come first."""
import re

DOMAINS = ("mobile", "frontend", "backend", "fullstack", "software", "data", "devops", "security", "qa", "embedded", "design", "product", "other")

_R = lambda p: re.compile(p, re.I)
TITLE_RULES = [
    ("mobile", _R(r"\b(ios|android|flutter|react[- ]native|swift(ui)?|kotlin|xamarin|app developer|mobile (app|apps|application|developer|engineer|dev|development|software|sdk|platform|team))\b")),
    ("security", _R(r"\b(security|cyber|pentest\w*|penetration|infosec|soc analyst|appsec|devsecops)\b")),
    ("devops", _R(r"\b(devops|sre|site reliability|platform engineer|infrastructure|cloud engineer|kubernetes|sysadmin|system administrator|release engineer|dev ?ops)\b")),
    ("data", _R(r"\b(data (engineer|scientist|analyst)|machine learning|\bml\b|\bai\b|llm|nlp|computer vision|deep learning|analytics|business intelligence|\bbi\b|mlops|data)\b")),
    ("qa", _R(r"\b(qa|quality assurance|test (engineer|automation|analyst)|tester|sdet)\b")),
    ("embedded", _R(r"\b(embedded|firmware|fpga|hardware|robotics|plc|automotive software|c/c\+\+ engineer)\b")),
    ("design", _R(r"\b(ux|ui designer|ui/ux|product designer|interaction designer|ux researcher)\b")),
    ("product", _R(r"\b(product (manager|owner)|scrum master|project manager|delivery manager|agile coach)\b")),
    ("fullstack", _R(r"\b(full[- ]?stack)\b")),
    ("frontend", _R(r"\b(front[- ]?end|react|angular|vue|web developer|javascript|typescript|ui engineer|ui developer)\b")),
    ("backend", _R(r"\b(back[- ]?end|java|python|golang|\bgo\b|\.net|c#|php|ruby|rails|node(\.?js)?|scala|rust|api|server[- ]side)\b")),
]
DESC_RULES = [
    ("mobile", _R(r"\b(ios|android|flutter|react native|swiftui|kotlin multiplatform)\b"), 3),
    ("frontend", _R(r"\b(react|angular|vue\.?js|svelte|css|html)\b"), 4),
    ("backend", _R(r"\b(spring|django|fastapi|express|rails|laravel|\.net core|microservices|postgres|rest api|grpc)\b"), 4),
    ("devops", _R(r"\b(terraform|kubernetes|ci/cd|ansible|helm|aws|gcp|azure)\b"), 4),
    ("data", _R(r"\b(spark|airflow|dbt|pytorch|tensorflow|pandas|snowflake|etl)\b"), 3),
]


GENERIC = _R(r"\b(software (engineer|developer)|developer|programmer|engineer)\b")


def classify(title: str, desc: str = "", skills: list[str] | None = None) -> str:
    t = title or ""
    for name, rx in TITLE_RULES:
        if rx.search(t): return name
    hay = f"{(desc or '')[:3000]} {' '.join(skills or [])}"
    best, score = "other", 0
    for name, rx, need in DESC_RULES:
        n = len(set(m.lower() for m in rx.findall(hay)))
        if n >= need and n > score: best, score = name, n
    if best == "other" and GENERIC.search(t): return "software"          # "Software Engineer" with no stack hint: general software role
    return best


def parse(csv: str) -> set[str]:
    """'mobile, backend' -> {'mobile','backend'} (unknown names are ignored; empty set = keep everything)."""
    return {d.strip().lower() for d in (csv or "").split(",") if d.strip().lower() in DOMAINS}
