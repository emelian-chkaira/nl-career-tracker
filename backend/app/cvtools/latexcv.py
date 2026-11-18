"""LaTeX side of the CV engine.

 1. `to_latex(cv)`      structured CV -> ATS-friendly single-column LaTeX (same section order/titles/grouping as the source).
                        This is how an uploaded PDF becomes LaTeX.
 2. `parse_latex(src)`  LaTeX CV (Jake's resume, moderncv/awesome-cv `\\cventry`, or plain article) -> the same structured dict.
 3. `tailor_latex(src, keywords)`  re-orders entries / bullets / skill lists *inside the original source*, so the user's own template,
                        macros and wording are preserved ("rebuild it the same way"). Nothing is added or reworded.
 4. `compile_pdf(src)`  optional: tectonic/pdflatex with shell-escape disabled, after rejecting dangerous primitives."""
import re, os, shutil, subprocess, tempfile, threading
from . import cv as cvmod
from app.core.config import settings
from .cv import _EMAIL

# ------------------------------------------------------------------ helpers
_ESC = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
def esc(s: str) -> str:
    s = (s or "").replace("\u2013", "--").replace("\u2014", "---").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", "``").replace("\u201d", "''").replace("\u2022", "-").replace("\u00a0", " ")
    return "".join(_ESC.get(ch, ch) for ch in s)

def read_group(s: str, i: int):
    """s[i] must be '{' -> (inner, index after the matching '}')."""
    depth, j = 0, i
    while j < len(s):
        ch = s[j]
        if ch == "\\": j += 2; continue
        if ch == "{": depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0: return s[i + 1:j], j + 1
        j += 1
    return s[i + 1:], len(s)

def read_args(s: str, i: int, n: int):
    args = []
    for _ in range(n):
        while i < len(s) and s[i] in " \t\n\r": i += 1
        if i < len(s) and s[i] == "[":                      # optional argument
            k = s.find("]", i); i = k + 1 if k > 0 else i + 1
            while i < len(s) and s[i] in " \t\n\r": i += 1
        if i >= len(s) or s[i] != "{": break
        a, i = read_group(s, i); args.append(a)
    return args, i

def strip_comments(s: str) -> str: return re.sub(r"(?<!\\)%.*", "", s)

_SIMPLE = [(r"\\textbf\*?\{", ""), (r"\\textit\{", ""), (r"\\emph\{", ""), (r"\\underline\{", ""), (r"\\textsc\{", ""), (r"\\texttt\{", ""), (r"\\small\b|\\large\b|\\Large\b|\\LARGE\b|\\Huge\b|\\huge\b|\\normalsize\b|\\footnotesize\b|\\scshape\b|\\bfseries\b|\\itshape\b|\\raggedright\b|\\centering\b", "")]
def _hrefs(t: str) -> str:
    out, i = [], 0
    while True:
        k = t.find("\\href{", i)
        if k < 0: out.append(t[i:]); break
        out.append(t[i:k]); url, j = read_group(t, k + 5)
        while j < len(t) and t[j] in " \t": j += 1
        if j < len(t) and t[j] == "{": label, j = read_group(t, j)
        else: label = url
        lab = re.sub(r"\s+", " ", to_text(label).replace("\n", " ")).strip()
        out.append(f"[{lab}]({url})" if url.startswith("http") and lab else lab)
        i = j
    return "".join(out)

def to_text(t: str) -> str:
    """LaTeX fragment -> readable text (keeps line structure; \\hfill -> two spaces)."""
    t = strip_comments(t)
    t = re.sub(r"\\(?:color|textcolor)\{[^}]*\}", " ", t).replace("\\ ", " ")
    t = _hrefs(t)                                                      # \href{url}{text} -> [text](url)
    t = t.replace("\\sep", " \u2022 ").replace("\\textbullet", "\u2022").replace("\\enspace", " ")
    t = re.sub(r"\\url\{([^}]*)\}", r"\1", t)
    t = re.sub(r"\\(?:vspace|hspace)\*?\{[^}]*\}", " ", t)
    t = re.sub(r"\\(?:hfill|quad|qquad|dotfill)\b", "  ", t)
    t = re.sub(r"\$\s*\\?\|\s*\$|\\textbar\{?\}?", " | ", t)
    t = re.sub(r"\\\\(?:\[[^\]]*\])?", "\n", t)
    for pat, rep in _SIMPLE: t = re.sub(pat, rep, t)
    t = re.sub(r"\\(?:textbackslash)\{\}", r"\\", t)
    t = t.replace("\\&", "&").replace("\\%", "%").replace("\\$", "$").replace("\\#", "#").replace("\\_", "_").replace("\\{", "{").replace("\\}", "}").replace("~", " ")
    t = t.replace("---", "—").replace("--", "–").replace("``", '"').replace("''", '"')
    t = re.sub(r"\\[a-zA-Z]+\*?(\[[^\]]*\])?", " ", t)                  # remaining commands
    t = t.replace("{", "").replace("}", "")
    return re.sub(r"[ \t]+", " ", t).strip()

# ------------------------------------------------------------------ safety
FORBIDDEN = re.compile(r"\\(input|include|includeonly|openin|openout|read|readline|write|immediate|catcode|csname|directlua|luaexec|special|pdfshellescape|ShellEscape|InputIfFileExists|lstinputlisting|verbatiminput|VerbatimInput)\b|\\def\\|\\newwrite|\\write18|\\usepackage\s*(\[[^\]]*\])?\s*\{[^}]*(shellesc|minted|pythontex|catchfile|verbatimbox|pdfpages)[^}]*\}", re.I)
def is_safe(src: str) -> bool:
    t = strip_comments(src).replace(r"\input{glyphtounicode}", "")            # the one harmless \input used by common ATS templates
    return not FORBIDDEN.search(t) and len(t) < 200_000

# ------------------------------------------------------------------ generator (structured CV -> LaTeX)
PREAMBLE = r"""\documentclass[letterpaper,11pt]{article}
\usepackage{latexsym}
\usepackage[empty]{fullpage}
\usepackage{titlesec}
\usepackage[usenames,dvipsnames]{color}
\usepackage{enumitem}
\usepackage[hidelinks]{hyperref}
\usepackage{iftex}
\ifPDFTeX \input{glyphtounicode}\pdfgentounicode=1 \fi
\pagestyle{empty}
\addtolength{\oddsidemargin}{-0.5in}\addtolength{\evensidemargin}{-0.5in}\addtolength{\textwidth}{1in}
\addtolength{\topmargin}{-.5in}\addtolength{\textheight}{1.0in}
\urlstyle{same}\raggedbottom\raggedright\setlength{\tabcolsep}{0in}
\titleformat{\section}{\vspace{-4pt}\scshape\raggedright\large}{}{0em}{}[\color{black}\titlerule \vspace{-5pt}]
\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-2pt}}}
\newcommand{\resumeSubheading}[4]{\vspace{-2pt}\item
  \begin{tabular*}{0.97\textwidth}[t]{l@{\extracolsep{\fill}}r}
    \textbf{#1} & #2 \\ \textit{\small#3} & \textit{\small #4} \\
  \end{tabular*}\vspace{-7pt}}
\newcommand{\resumeProjectHeading}[2]{\item
  \begin{tabular*}{0.97\textwidth}{l@{\extracolsep{\fill}}r}
    \small#1 & #2 \\
  \end{tabular*}\vspace{-7pt}}
\renewcommand\labelitemii{$\vcenter{\hbox{\tiny$\bullet$}}$}
\newcommand{\resumeSubHeadingListStart}{\begin{itemize}[leftmargin=0.15in, label={}]}
\newcommand{\resumeSubHeadingListEnd}{\end{itemize}}
\newcommand{\resumeItemListStart}{\begin{itemize}}
\newcommand{\resumeItemListEnd}{\end{itemize}\vspace{-5pt}}
"""
_DEF_TITLES = {"summary": "Summary", "experience": "Experience", "education": "Education", "skills": "Technical Skills", "projects": "Projects", "languages": "Languages", "references": "References", "certifications": "Certifications"}

def _split_heading(h: str):
    """'Org | Role | City  2022 - 2024' -> (org, date, role, loc)"""
    h = h or ""
    m = cvmod.DATE_RE.search(h)
    date = m.group(0).strip() if m else ""
    rest = h.replace(m.group(0), "") if m else h
    if not m:                                           # single year / 'Month YYYY' tail, or anything after a column gap
        t = re.search(r"\s{2,}((?:(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+)?(?:19|20)\d{2}|present)\s*$", h, re.I)
        if t: date, rest = t.group(1), h[:t.start()]
    rest = rest.strip(" |-–—,")
    parts = [p.strip(" -–—,") for p in re.split(r"\s*\|\s*|\s+[-–—]\s+", rest) if p.strip(" -–—,")]
    if len(parts) == 1 and "," in parts[0] and len(parts[0]) > 40:
        parts = [p.strip() for p in parts[0].split(",", 1)]
    return (parts[0] if parts else ""), date, (parts[1] if len(parts) > 1 else ""), (", ".join(parts[2:]) if len(parts) > 2 else "")

def _entries(blocks, project=False):
    out = ["  \\resumeSubHeadingListStart"]
    for b in blocks:
        org, date, role, loc = _split_heading(b["heading"])
        out.append(f"    \\resumeProjectHeading{{\\textbf{{{esc(org)}}}{(' $|$ \\emph{' + esc(role) + '}') if role else ''}}}{{{esc(date)}}}" if project else
                   f"    \\resumeSubheading{{{esc(org)}}}{{{esc(date)}}}{{{esc(role)}}}{{{esc(loc)}}}")
        if b["bullets"]:
            out.append("      \\resumeItemListStart"); out += [f"        \\resumeItem{{{esc(x)}}}" for x in b["bullets"]]; out.append("      \\resumeItemListEnd")
    out.append("  \\resumeSubHeadingListEnd")
    return "\n".join(out)

def to_latex_jake(cv: dict) -> str:
    """Structured CV -> LaTeX; keeps the section order and titles of the original CV."""
    order = [k for k in (cv.get("order") or []) if k in _DEF_TITLES or k.startswith("x:")] or ["summary", "experience", "education", "projects", "skills"]
    for k in ("experience", "education", "projects", "skills", "summary", "languages", "certifications", "references"):
        if k not in order and (cv.get(k) or (k == "skills" and cv.get("skills"))): order.append(k)
    titles = cv.get("titles") or {}
    contact = [esc(x) for x in (cv.get("phone"), cv.get("location")) if x]
    if cv.get("email"): contact.append(f"\\href{{mailto:{cv['email']}}}{{{esc(cv['email'])}}}")
    for l in cv.get("links", []): contact.append(f"\\href{{{l if l.startswith('http') else 'https://' + l}}}{{{esc(re.sub(r'^https?://(www\\.)?', '', l))}}}")
    o = [PREAMBLE, r"\begin{document}", r"\begin{center}", f"    {{\\Huge \\scshape {esc(cv.get('name') or 'Your Name')}}} \\\\ \\vspace{{1pt}}", "    \\small " + " $|$ ".join(contact), r"\end{center}"]
    for k in order:
        title = esc(titles.get(k) or _DEF_TITLES.get(k, k))
        if k == "summary" and cv.get("summary"): o += [f"\\section{{{title}}}", esc(cv["summary"])]
        elif k in ("experience", "education", "projects") and cv.get(k): o += [f"\\section{{{title}}}", _entries(cv[k], project=(k == "projects"))]
        elif k == "skills" and (cv.get("skills") or cv.get("skill_groups")):
            groups = cv.get("skill_groups") or [{"label": "Skills", "items": cv["skills"]}]
            o += [f"\\section{{{title}}}", r"\begin{itemize}[leftmargin=0.15in, label={}]", r"  \small{\item{"]
            o += [f"    \\textbf{{{esc(g['label'])}}}{{: {', '.join(esc(x) for x in g['items'])}}} \\\\" for g in groups]
            o += [r"  }}", r"\end{itemize}"]
        elif k == "languages" and cv.get("languages"): o += [f"\\section{{{title}}}", "\\begin{itemize}[leftmargin=0.15in, label={}]", "  \\small{\\item{", *[f"    {esc(x)} \\\\" for x in cv["languages"]], "  }}", "\\end{itemize}"]
        elif k == "references" and cv.get("references"): o += [f"\\section{{{title}}}", "\\begin{itemize}[leftmargin=0.15in, label={}]", "  \\small{\\item{", *[f"    {esc(x)} \\\\" for x in cv["references"]], "  }}", "\\end{itemize}"]
        elif k == "certifications" and cv.get("certifications"): o += [f"\\section{{{title}}}", "\\resumeItemListStart", *[f"  \\resumeItem{{{esc(c)}}}" for c in cv["certifications"]], "\\resumeItemListEnd"]
        elif k.startswith("x:"):
            ex = next((e for e in cv.get("extras", []) if e["title"] == k[2:]), None)
            if ex: o += [f"\\section{{{esc(ex['title'])}}}", _entries(ex["blocks"])]
    for e in cv.get("extras", []):
        if f"x:{e['title']}" not in order and e["blocks"]: o += [f"\\section{{{esc(e['title'])}}}", _entries(e["blocks"])]
    o.append(r"\end{document}")
    return "\n".join(o) + "\n"

# ------------------------------------------------------------------ faithful generator (same look as a hand-written CV)
PREAMBLE2 = r"""\documentclass[10pt, a4paper]{article}

\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage[margin=1.7cm, top=1.5cm, bottom=1.6cm]{geometry}
\usepackage{parskip}
\usepackage{titlesec}
\usepackage{enumitem}
\usepackage[svgnames]{xcolor}
\usepackage{hyperref}
\usepackage{tabularx}
\usepackage{array}
\usepackage{fancyhdr}

\definecolor{accent}{HTML}{0E7490}
\definecolor{soft}{HTML}{6B7280}

\hypersetup{colorlinks=true, urlcolor=accent, linkcolor=accent, pdfborder={0 0 0},
  pdftitle={@@TITLE@@}, pdfauthor={@@AUTHOR@@}}

\titleformat{\section}{\normalsize\bfseries\color{accent}}{}{0em}{\MakeUppercase}
  [\vspace{1pt}{\color{soft!40}\hrule height 0.5pt}\vspace{4pt}]
\titlespacing{\section}{0pt}{7pt}{2pt}

\setlist[itemize]{leftmargin=1.3em, itemsep=1pt, topsep=1pt, parsep=0pt}

\pagestyle{fancy}
\fancyhf{}
\renewcommand{\headrulewidth}{0pt}
@@FOOTER@@

% {Title}{Place}{Dates}
\newcommand{\entry}[3]{%
  \noindent
  \begin{tabularx}{\linewidth}{@{}X r@{}}
    \textbf{#1} & {\small\color{soft}#3} \\
    \multicolumn{2}{@{}l@{}}{\small\color{soft}\textit{#2}} \\
  \end{tabularx}\par\vspace{1pt}%
}

% {Name -- tagline}{meta (region, stats)}{links}{description}{tech}
\newcommand{\project}[5]{%
  \noindent\textbf{#1} \enspace{\small #3} \hfill {\small\color{soft}#2}\\
  {\small #4}\ifx\relax#5\relax\else{} {\footnotesize\color{soft}-- #5}\fi\par\vspace{3pt}%
}

\newcommand{\sep}{\quad\textbullet\quad}

\begin{document}
"""
_RICH = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)|\*\*(.+?)\*\*")
def _plain_esc(t: str) -> str:
    t = t.replace("\u2022", "\x00").replace("\u2013", "--").replace("\u2014", "---").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", "``").replace("\u201d", "''").replace("\u00a0", " ")
    t = re.sub(r"(?<=\s)-(?=\s)", "--", t)
    return "".join(_ESC.get(ch, ch) for ch in t).replace("\x00", r"\textbullet{}")
def _url(u: str) -> str: return u.replace("\\", "").replace("%", r"\%").replace("#", r"\#").replace("{", "%7B").replace("}", "%7D")
def rich(s: str) -> str:
    """Text with [label](url) and **bold** markup -> LaTeX (\\href / \\textbf); everything else is escaped."""
    out, pos = [], 0
    for m in _RICH.finditer(s or ""):
        out.append(_plain_esc(s[pos:m.start()]))
        out.append(f"\\href{{{_url(m.group(2))}}}{{{_plain_esc(m.group(1))}}}" if m.group(1) else f"\\textbf{{{rich(m.group(3))}}}")
        pos = m.end()
    out.append(_plain_esc((s or "")[pos:]))
    return "".join(out)
def _title_case(t: str) -> str:
    return " ".join(w if (len(w) <= 2 or not w.isupper()) else w.capitalize() for w in t.split()) if t.isupper() else t
def _links_tex(links) -> str: return r" \sep ".join(f"\\href{{{_url(l['url'])}}}{{{_plain_esc(l['label'])}}}" for l in links)

def _blocks_tex(blocks) -> list[str]:
    o = []
    for b in blocks:
        title, place, date = b.get("title") or b.get("heading", ""), b.get("place", ""), b.get("date", "")
        if b.get("kind") == "project":
            o.append(f"\\project{{{rich(title)}}}{{{rich(b.get('meta', ''))}}}\n  {{{_links_tex(b.get('links', []))}}}\n  {{{rich(b.get('desc', ''))}}}\n  {{{rich(b.get('tech', ''))}}}\n")
            if b.get("bullets"): o[-1] += "\\begin{itemize}\n" + "\n".join(f"  \\item {rich(x)}" for x in b["bullets"]) + "\n\\end{itemize}\n"
            continue
        if not place and " | " in title: title, place = (x.strip() for x in title.split(" | ", 1))
        o.append(f"\\entry{{{rich(title)}}}{{{rich(place)}}}{{{rich(date)}}}")
        if b.get("desc"):
            long = len(b["desc"]) > 230
            o.append(f"\\vspace{{-2pt}}\n{rich(b['desc'])}" if long else f"\\vspace{{-5pt}}{{\\small {rich(b['desc'])}}}\\par\\vspace{{3pt}}")
        if b.get("bullets"): o += ["\\begin{itemize}", *[f"  \\item {rich(x)}" for x in b["bullets"]], "\\end{itemize}"]
        if b.get("links") and b.get("kind") != "project": o.append(("\\noindent " if b.get("desc") else "") + _links_tex(b["links"]) + "\n")
        elif not b.get("desc") and not b.get("bullets"): o.append("")
        o.append("")
    return o

def _header_tex(cv: dict) -> list[str]:
    h = cv.get("header") or {}
    name = rich(cv.get("name") or "Your Name")
    o = ["", "% ---- HEADER ----", "\\noindent", "\\begin{minipage}[c]{\\linewidth}", f"  {{\\LARGE\\bfseries {name}}}\\\\[4pt]"]
    tag = h.get("tagline") or []
    for i, t in enumerate(tag[:3]):
        t = " \\ \\textbar{} \\ ".join(rich(x.strip()) for x in re.split(r"\s*\|\s*", t))
        o.append(f"  {{\\normalsize {t}}}\\\\[3pt]" if i == 0 else f"  {{\\small\\color{{soft}}{t}}}\\\\[3pt]")
    contact = h.get("contact") or []
    if not contact:                                                   # not from a layout-aware PDF: rebuild from the plain fields
        items = [rich(cv.get("location", "")), (f"\\href{{tel:{re.sub(r'[^+0-9]', '', cv['phone'])}}}{{{rich(cv['phone'])}}}" if cv.get("phone") else ""),
                 (f"\\href{{mailto:{cv['email']}}}{{{rich(cv['email'])}}}" if cv.get("email") else "")]
        links = [f"\\href{{{l if l.startswith('http') else 'https://' + l}}}{{{_plain_esc(re.sub(r'^https?://(www\.)?', '', l))}}}" for l in cv.get("links", [])]
        contact_tex = [r" \sep ".join(x for x in items if x), r" \sep ".join(links)]
    else:
        contact_tex = []
        for line in contact:
            parts = []
            for it in re.split(r"\s*•\s*", line):
                if _EMAIL.fullmatch(it.strip()): parts.append(f"\\href{{mailto:{it.strip()}}}{{{_plain_esc(it.strip())}}}")
                elif re.fullmatch(r"\+?[\d ()\-]{8,}", it.strip()): parts.append(f"\\href{{tel:{re.sub(r'[^+0-9]', '', it)}}}{{{_plain_esc(it.strip())}}}")
                else: parts.append(rich(it))
            contact_tex.append(r" \sep ".join(parts))
    contact_tex = [c for c in contact_tex if c]
    if contact_tex: o.append("  {\\small\\raggedright " + "\\\\[2pt]\n    ".join(contact_tex) + "\\par}")
    o.append("\\end{minipage}")
    if h.get("note"): o += ["", "\\vspace{4pt}", "\\noindent{\\small " + rich(h["note"]) + "}"]
    return o + [""]

def to_latex(cv: dict) -> str:
    """Structured CV -> LaTeX in the same visual style as a hand-written CV: header block, accent-coloured section rules, \\entry / \\project rows,
    a labelled skills table, working hyperlinks and a running footer. Section order and titles follow the source."""
    order = [k for k in (cv.get("order") or []) if k in _DEF_TITLES or k.startswith("x:")] or ["summary", "experience", "education", "projects", "skills"]
    for k in ("summary", "experience", "education", "projects", "skills", "languages", "certifications"):
        if k not in order and cv.get(k): order.append(k)
    titles = cv.get("titles") or {}
    name = (cv.get("name") or "").strip()
    footer = cv.get("footer") or ""
    foot = (f"\\fancyfoot[C]{{\\footnotesize\\color{{soft}}{rich(footer.replace(' - ', ' -- '))}}}" if footer else "")
    o = [PREAMBLE2.replace("@@TITLE@@", _plain_esc(f"{name} -- CV").replace("\\", "")).replace("@@AUTHOR@@", _plain_esc(name).replace("\\", "")).replace("@@FOOTER@@", foot)]
    o += _header_tex(cv)
    langs_done = False
    for k in order:
        title = rich(_title_case(titles.get(k) or _DEF_TITLES.get(k, k)))
        if k == "summary" and cv.get("summary"): o += [f"\\section{{{title}}}", "", rich(cv["summary"]), ""]
        elif k in ("experience", "education", "projects") and cv.get(k): o += [f"\\section{{{title}}}", "", *_blocks_tex(cv[k])]
        elif k == "skills" and (cv.get("skill_groups") or cv.get("skills")):
            groups = cv.get("skill_groups") or [{"label": "Skills", "items": cv["skills"]}]
            o += [f"\\section{{{title}}}", "", r"\begin{tabularx}{\linewidth}{@{} >{\bfseries}p{3.4cm} X @{}}"]
            o += [f"  {rich(g['label'])} & {', '.join(rich(x) for x in g['items'])} \\\\[2pt]" for g in groups]
            o += [r"\end{tabularx}", ""]
        elif k == "languages" and (cv.get("languages") or cv.get("references")):
            o += [f"\\section{{{title}}}", ""]
            if cv.get("languages"): o += ["\\noindent " + r" \sep ".join(rich(x) for x in cv["languages"]), ""]
            for r in cv.get("references") or []: o += ["\\vspace{6pt}", "\\noindent{\\small\\color{soft}" + rich(r) + "}", ""]
            langs_done = True
        elif k == "certifications" and cv.get("certifications"): o += [f"\\section{{{title}}}", "", "\\begin{itemize}", *[f"  \\item {rich(c)}" for c in cv["certifications"]], "\\end{itemize}", ""]
        elif k.startswith("x:"):
            ex = next((e for e in cv.get("extras", []) if e["title"] == k[2:]), None)
            if ex: o += [f"\\section{{{title}}}", "", *_blocks_tex(ex["blocks"])]
    if cv.get("references") and not langs_done:
        o += ["\\section{References}", ""] + [f"\\noindent{{\\small {rich(r)}}}\n" for r in cv["references"]]
    for e in cv.get("extras", []):
        if f"x:{e['title']}" not in order and e["blocks"]: o += [f"\\section{{{rich(_title_case(e['title']))}}}", "", *_blocks_tex(e["blocks"])]
    o.append(r"\end{document}")
    return "\n".join(o) + "\n"

# ------------------------------------------------------------------ parser (LaTeX -> structured CV)
SEC_RE = re.compile(r"\\(?:section|cvsection|sectionTitle)\*?\s*(?:\[[^\]]*\])?\s*\{")
def _tables(body: str) -> str:
    """tabularx/tabular rows ('label & items \\\\') -> bold label + two-space column gap, so skills tables parse like layout rows."""
    out, i = [], 0
    pat = re.compile(r"\\begin\{(tabularx|tabular)\}")
    while True:
        m = pat.search(body, i)
        if not m: out.append(body[i:]); break
        out.append(body[i:m.start()]); j = m.end()
        _, j = read_args(body, j, 2 if m.group(1) == "tabularx" else 1)
        e = body.find("\\end{" + m.group(1) + "}", j)
        if e < 0: out.append(body[j:]); break
        rows = re.split(r"\\\\(?:\[[^\]]*\])?", body[j:e])
        for r in rows:
            if r.strip(): out.append("\n" + (r.replace("\\&", "\x00").replace("&", "\x06", 1) if "&" in r else r).replace("\x00", "\\&").lstrip() + "\\\\\n" if False else "\n\x01" + re.sub(r"(?<!\\)&", "\x06", r, count=1).strip() + "\n")
        i = e + len("\\end{" + m.group(1) + "}")
    return "".join(out)

def _macros_to_text(body: str) -> str:
    """Rewrite known CV macros to the plain-text conventions cv.py parses ('\\x01' bold entry line, '- ' bullets)."""
    body = _tables(strip_comments(body)); out, i = [], 0
    pat = re.compile(r"\\(entry|project|resumeSubheading|resumeSubSubheading|resumeProjectHeading|cventry|cvitem|cvdoubleitem|cvlistitem|resumeItem|resumeSubItem|item|resumeSubHeadingListStart|resumeSubHeadingListEnd|resumeItemListStart|resumeItemListEnd|cvskills)\b\*?")
    while True:
        m = pat.search(body, i)
        if not m: out.append(body[i:]); break
        out.append(body[i:m.start()]); name = m.group(1); j = m.end()
        n = {"entry": 3, "project": 5, "resumeSubheading": 4, "resumeSubSubheading": 2, "resumeProjectHeading": 2, "cventry": 6, "cvitem": 2, "cvdoubleitem": 4, "cvlistitem": 1, "resumeItem": 1, "resumeSubItem": 1}.get(name, 0)
        if n:
            args, j = read_args(body, j, n); a = [to_text(x).replace("\n", " ").strip() for x in args] + [""] * n
            if name == "entry": out.append("\n\x01" + a[0] + "\x06" + a[2] + "\n" + a[1] + "\n")
            elif name == "project": out.append("\n\x01" + a[0] + ("\x06" + a[2] if a[2] else "") + ("\x06" + a[1] if a[1] else "") + "\n" + a[3] + (" - " + a[4] if a[4] else "") + "\n")
            elif name == "resumeSubheading": out.append("\n\x01" + " | ".join(x for x in (a[0], a[2], a[3]) if x) + "\x06" + a[1] + "\n")
            elif name == "resumeSubSubheading": out.append("\n\x01" + a[0] + "\x06" + a[1] + "\n")
            elif name == "resumeProjectHeading": out.append("\n\x01" + a[0] + "\x06" + a[1] + "\n")
            elif name == "cventry": out.append("\n\x01" + " | ".join(x for x in (a[1], a[2], a[3]) if x) + "\x06" + a[0] + "\n" + ("- " + a[5] + "\n" if a[5] else ""))
            elif name == "cvitem": out.append(f"\n{a[0]}: {a[1]}\n")
            elif name == "cvdoubleitem": out.append(f"\n{a[0]}: {a[1]}\n{a[2]}: {a[3]}\n")
            elif name == "cvlistitem": out.append("\n- " + a[0] + "\n")
            else: out.append("\n- " + a[0] + "\n")                                   # resumeItem / resumeSubItem
        elif name == "item":
            out.append("\n- ")
        i = j
    t = "".join(out)
    t = re.sub(r"\\begin\{(itemize|enumerate)\}(\[[^\]]*\])?|\\end\{(itemize|enumerate)\}|\\begin\{center\}|\\end\{center\}", "\n", t)
    # remaining inline markup; keep our markers
    lines = [(to_text(l) if not l.startswith("\x01") else "\x01" + to_text(l[1:])).replace("\x06", "  ") for l in t.split("\n")]
    out2 = []
    for l in lines:                                   # blank lines only between entries (LaTeX puts them between bullets too)
        if not l.strip(): continue
        if l.startswith("\x01") and out2: out2.append("")
        out2.append(l)
    return "\n".join(out2)

def _expand_macros(s: str) -> str:
    """Substitute zero-argument \\newcommand{\\name}{value} definitions (e.g. \\portfoliourl) so links built from them are not lost."""
    defs = {}
    for m in re.finditer(r"\\(?:newcommand|renewcommand)\*?\{\\([A-Za-z]+)\}(?!\[)\s*\{", s):
        val, _ = read_group(s, m.end() - 1)
        if len(m.group(1)) >= 4 and "\\" not in val.replace("\\&", "").replace("\\_", "") and m.group(1) not in ("sep", "entry", "project"): defs[m.group(1)] = val
    b = s.find(r"\begin{document}")
    head, body = (s[:b], s[b:]) if b >= 0 else ("", s)
    for k, v in defs.items(): body = re.sub(r"\\" + k + r"(?![A-Za-z])", lambda _m, v=v: v, body)
    return head + body

def parse_latex(src: str) -> dict:
    s = _expand_macros(strip_comments(src))
    b = s.find(r"\begin{document}"); body = s[b + len(r"\begin{document}"):] if b >= 0 else s
    body = body.split(r"\end{document}")[0]
    secs = [(m.start(), m.end()) for m in SEC_RE.finditer(body)]
    header = body[:secs[0][0]] if secs else body[:600]
    name = ""
    m = re.search(r"\\(?:Huge|huge|LARGE|Large)\b(.*?)\}", header, re.S)
    if m: name = to_text(m.group(1)).split("\n")[0].strip()
    mm = re.search(r"\\name\{([^}]*)\}\{([^}]*)\}", s)
    if mm and not name: name = (mm.group(1) + " " + mm.group(2)).strip()
    if not name:
        for l in to_text(header).split("\n"):
            l = l.strip()
            if 2 <= len(l.split()) <= 4 and not re.search(r"[\d@|]", l): name = l; break
    extra_head = " ".join(re.findall(r"\\(?:email|phone|social|homepage|address|extrainfo)(?:\[[^\]]*\])?\{([^}]*)\}", s))
    sections = {}; order, titles, extras = [], {}, []
    for idx, (st, en) in enumerate(secs):
        title_raw, after = read_group(body, en - 1)
        title = to_text(title_raw).strip()
        end = secs[idx + 1][0] if idx + 1 < len(secs) else len(body)
        txt = _macros_to_text(body[after:end]).split("\n")
        key = next((k for k, r in cvmod.HEAD_RE.items() if r.match(title.lower())), None)
        if key is None and re.search(r"skill|technolog|tech stack|tools", title, re.I): key = "skills"
        if key is None and re.search(r"experience|employment|work", title, re.I): key = "experience"
        if key is None and re.search(r"education|academic", title, re.I): key = "education"
        if key is None and re.search(r"project", title, re.I): key = "projects"
        if key and key != "other":
            sections[key] = sections.get(key, []) + txt
            if key not in order: order.append(key); titles[key] = title
        else: extras.append((title, txt)); order.append("x:" + title); titles["x:" + title] = title
    hdr = re.sub(r"\\(?:begin|end)\{minipage\}(\[[^\]]*\])?(\{[^{}]*\})?|\\includegraphics(\[[^\]]*\])?\{[^}]*\}|\\hfill|\\par\b", " ", header)
    hdr = re.sub(r"(?<!\n)\n(?!\n)", " ", hdr)
    sections["header"] = [l for l in to_text(hdr).split("\n") if l.strip()]
    flat = "\n".join([to_text(header), extra_head] + [l for ls in sections.values() for l in ls])
    cv = cvmod.build_cv(sections, order, titles, extras, flat, header_name=name)
    mail = re.search(r"mailto:([^}\s]+)", s)
    if mail and not cv["email"]: cv["email"] = mail.group(1)
    urls = re.findall(r"\\href\{(https?://[^}]*)\}", s)
    cv["links"] = list(dict.fromkeys(cv["links"] + [u for u in urls if re.search(r"linkedin|github|gitlab|portfolio|\.dev|\.io", u, re.I)]))
    return cv

# ------------------------------------------------------------------ in-place tailoring
ENTRY_RE = re.compile(r"\\(resumeSubheading|resumeProjectHeading|cventry|entry|project)\b")
ITEM_LIST_RE = re.compile(r"(\\resumeItemListStart)(.*?)(\\resumeItemListEnd)|(\\begin\{itemize\}(?:\[[^\]]*\])?)((?:(?!\\begin\{itemize\}).)*?)(\\end\{itemize\})", re.S)
SKIP_SECTIONS = re.compile(r"education|language|certif|reference|interest|hobb", re.I)

def _score(text: str, kw) -> int:
    """kw: {term: weight} (earlier job keywords weigh more)."""
    return sum(kw.get(t, 0) for t in set(cvmod.find_terms(to_text(text))))

def _item_spans(block: str):
    spans, i = [], 0
    pat = re.compile(r"\\(resumeItem|resumeSubItem)\b|\\item\b")
    ms = list(pat.finditer(block))
    for k, m in enumerate(ms):
        if m.group(1):
            _, e = read_args(block, m.end(), 1)
        else:
            e = ms[k + 1].start() if k + 1 < len(ms) else len(block)
        spans.append((m.start(), e))
    return spans

def _reorder_items(block: str, kset: set):
    spans = _item_spans(block)
    if len(spans) < 2: return block, 0
    texts = [block[a:b] for a, b in spans]
    order = sorted(range(len(texts)), key=lambda i: -_score(texts[i], kset))
    if all(_score(t, kset) == 0 for t in texts) or order == list(range(len(texts))): return block, 0
    out, pos = [], 0
    tails = [t[len(t.rstrip()):] for t in texts]                                  # keep each slot's own trailing whitespace
    for slot, ((a, b), idx) in enumerate(zip(spans, order)): out.append(block[pos:a]); out.append(texts[idx].rstrip() + tails[slot]); pos = b
    out.append(block[pos:])
    moved = sum(1 for i, j in enumerate(order) if i != j)
    return "".join(out), moved

def _reorder_lists(sec: str, kset: set):
    moved = 0
    def sub(m):
        nonlocal moved
        if m.group(1): head, inner, tail = m.group(1), m.group(2), m.group(3)
        else: head, inner, tail = m.group(4), m.group(5), m.group(6)
        inner2, n = _reorder_items(inner, kset); moved += n
        return head + inner2 + tail
    return ITEM_LIST_RE.sub(sub, sec), moved

def _reorder_entries(sec: str, kset: set):
    ms = list(ENTRY_RE.finditer(sec))
    if len(ms) < 2: return sec, 0
    end_m = re.search(r"\\resumeSubHeadingListEnd|\\end\{itemize\}\s*$", sec[ms[-1].start():])
    last_end = ms[-1].start() + (end_m.start() if end_m else len(sec) - ms[-1].start())
    bounds = [m.start() for m in ms] + [last_end]
    ents = [sec[bounds[i]:bounds[i + 1]] for i in range(len(ms))]
    sc = [_score(e, kset) for e in ents]
    order = sorted(range(len(ents)), key=lambda i: -sc[i])
    if not any(sc) or order == list(range(len(ents))): return sec, 0
    tails = [e[len(e.rstrip()):] for e in ents]
    return sec[:bounds[0]] + "".join(ents[i].rstrip() + tails[slot] for slot, i in enumerate(order)) + sec[last_end:], sum(1 for i, j in enumerate(order) if i != j)

LIST_RE = re.compile(r"(?<=[{:])([ \t]*[^{}\\\n:,()]+(?:,[^{}\\\n:()]+)+)(?=\s*(?:\}|\\\\|\n|$))")
def _reorder_skill_lists(sec: str, matched: set):
    moved = 0
    def sub(m):
        nonlocal moved
        items = [x.strip() for x in m.group(1).split(",")]
        key = lambda x: 0 if x.lower() in matched or any(len(k) > 2 and k in x.lower() for k in matched) else 1
        new = sorted(items, key=key)
        if new == items: return m.group(1)
        moved += 1
        return " " + ", ".join(new)
    return LIST_RE.sub(sub, sec), moved

def tailor_latex(src: str, keywords: list[str], matched: list[str]) -> tuple[str, list[str]]:
    """Re-order inside the user's own LaTeX. Only moves existing entries/bullets/skills; never edits or adds text."""
    kset, mset = {k: len(keywords) - i for i, k in enumerate(keywords)}, {m.lower() for m in matched}
    b = src.find(r"\begin{document}")
    pre, body = (src[:b], src[b:]) if b >= 0 else ("", src)
    ms = list(SEC_RE.finditer(body))
    if not ms: return src, []
    parts, changes, last = [body[:ms[0].start()]], [], ms[0].start()
    for idx, m in enumerate(ms):
        end = ms[idx + 1].start() if idx + 1 < len(ms) else len(body)
        sec = body[m.start():end]
        title = to_text(read_group(sec, m.end() - m.start() - 1)[0])
        if re.search(r"skill|technolog|tools|tech stack", title, re.I):
            sec, n = _reorder_skill_lists(sec, mset)
            if n: changes.append(f"{title}: matching skills moved to the front of {n} list(s)")
        elif not SKIP_SECTIONS.search(title):
            sec, ne = _reorder_entries(sec, kset); sec, nb = _reorder_lists(sec, kset)
            if ne: changes.append(f"{title}: reordered {ne} entries by relevance")
            if nb: changes.append(f"{title}: reordered {nb} bullets by relevance")
        parts.append(sec)
    out = pre + "".join(parts)
    return out, changes

# ------------------------------------------------------------------ compile
_slot = threading.Semaphore(2)
def compiler() -> str | None:
    if not settings.latex_compile: return None
    return shutil.which("tectonic") or shutil.which("pdflatex")

def compile_pdf(src: str, timeout: int = 120) -> tuple[bytes | None, str]:
    exe = compiler()
    if not exe: return None, "no LaTeX compiler available on this server — download the .tex and compile it (e.g. on Overleaf)"
    if not is_safe(src): return None, "LaTeX contains disallowed commands (\\input, \\write, \\catcode, …)"
    with _slot, tempfile.TemporaryDirectory(prefix="cvtex-") as d:
        with open(os.path.join(d, "cv.tex"), "w", encoding="utf8") as f: f.write(src)
        cmd = [exe, "-X", "compile", "--untrusted", "--outdir", d, "cv.tex"] if exe.endswith("tectonic") else [exe, "-no-shell-escape", "-interaction=nonstopmode", "-halt-on-error", "-output-directory", d, "cv.tex"]
        try: r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=timeout, env={**os.environ, "openin_any": "p", "openout_any": "p"})
        except subprocess.TimeoutExpired: return None, "LaTeX compilation timed out"
        pdf = os.path.join(d, "cv.pdf")
        if r.returncode == 0 and os.path.exists(pdf):
            return open(pdf, "rb").read(), ""
        return None, ("LaTeX error: " + ((r.stderr or r.stdout)[-400:])).strip()


# ------------------------------------------------------------------ public compilers (opt-in: the document leaves this server)
PUBLIC_SERVICES = {
    "ytotech": "https://latex.ytotech.com/builds/sync",        # open-source LaTeX-on-HTTP (YtoTech/docker-latex-on-http)
    "texlive": "https://texlive.net/cgi-bin/latexcgi",          # latexcgi, the TeX Live public service
}
def _post_ytotech(src: str, timeout: int):
    import httpx
    r = httpx.post(PUBLIC_SERVICES["ytotech"], timeout=timeout, json={"compiler": "pdflatex", "resources": [{"main": True, "content": src}]})
    if r.status_code in (200, 201) and r.content[:4] == b"%PDF": return r.content, ""
    return None, f"ytotech: HTTP {r.status_code} {r.text[:200]}"

def _post_texlive(src: str, timeout: int):
    import httpx
    r = httpx.post(PUBLIC_SERVICES["texlive"], timeout=timeout, follow_redirects=True,
                   data={"engine": "pdflatex", "return": "pdf"}, files={"filecontents[]": (None, src), "filename[]": (None, "document.tex")})
    if r.status_code == 200 and r.content[:4] == b"%PDF": return r.content, ""
    return None, f"texlive.net: HTTP {r.status_code} (LaTeX error in the document?)"

def compile_public(src: str, timeout: int = 90) -> tuple[bytes | None, str, str]:
    """Try each public service in turn -> (pdf, error, service). Never called unless the user consented to sending the CV to a third party."""
    if not is_safe(src): return None, "LaTeX contains disallowed commands (\\input, \\write, \\catcode, …)", ""
    errs = []
    for name, fn in (("ytotech", _post_ytotech), ("texlive", _post_texlive)):
        try:
            pdf, err = fn(src, timeout)
            if pdf: return pdf, "", name
            errs.append(err)
        except Exception as e: errs.append(f"{name}: {str(e)[:80]}")
    return None, " | ".join(errs), ""

def compile_any(src: str, mode: str = "auto") -> dict:
    """mode: 'local' (this server only) | 'public' (third-party service) | 'auto' (local first, then public only if the caller allowed it)."""
    out = {"pdf": None, "error": "", "engine": "", "local_available": bool(compiler())}
    if mode in ("local", "auto") and compiler():
        pdf, err = compile_pdf(src)
        if pdf: out.update(pdf=pdf, engine="local:" + os.path.basename(compiler())); return out
        out["error"] = err
    if mode == "public":
        pdf, err, svc = compile_public(src)
        if pdf: out.update(pdf=pdf, engine="public:" + svc, error="")
        else: out["error"] = err
    elif not out["error"]: out["error"] = "no LaTeX compiler available on this server"
    return out
