import io, re, pytest
from app.cvtools import cv, latexcv

JAKE = r"""
\documentclass[letterpaper,11pt]{article}
\usepackage{latexsym}
\input{glyphtounicode}
\newcommand{\resumeItem}[1]{\item\small{#1 \vspace{-2pt}}}
\newcommand{\resumeSubheading}[4]{\vspace{-2pt}\item \textbf{#1} & #2 \\ \textit{#3} & \textit{#4}}
\begin{document}
\begin{center}
    \textbf{\Huge \scshape John Smith} \\ \vspace{1pt}
    \small 06 12345678 $|$ \href{mailto:john@smith.nl}{john@smith.nl} $|$
    \href{https://linkedin.com/in/johnsmith}{linkedin.com/in/johnsmith} $|$ \href{https://github.com/jsmith}{github.com/jsmith}
\end{center}
\section{Education}
  \resumeSubHeadingListStart
    \resumeSubheading{Delft University of Technology}{Sep 2021 -- Jul 2025}{BSc Computer Science}{Delft, NL}
  \resumeSubHeadingListEnd
\section{Experience}
  \resumeSubHeadingListStart
    \resumeSubheading{Bank Corp}{Jun 2024 -- Aug 2024}{Data Intern}{Amsterdam, NL}
      \resumeItemListStart
        \resumeItem{Cleaned datasets with Pandas and SQL}
        \resumeItem{Organised the team offsite}
      \resumeItemListEnd
    \resumeSubheading{Shop BV}{Jan 2024 -- Mar 2024}{Mobile Developer Intern}{Utrecht, NL}
      \resumeItemListStart
        \resumeItem{Fixed UI bugs}
        \resumeItem{Built a \textbf{Flutter} checkout screen with Dart}
      \resumeItemListEnd
  \resumeSubHeadingListEnd
\section{Technical Skills}
 \begin{itemize}[leftmargin=0.15in, label={}]
    \small{\item{
     \textbf{Languages}{: SQL, Java, Dart, Python} \\
     \textbf{Frameworks}{: Django, Flutter, React}
    }}
 \end{itemize}
\end{document}
"""

MODERN = r"""
\documentclass[11pt,a4paper]{moderncv}
\moderncvstyle{classic}
\name{Anna}{Jansen}
\email{anna@jansen.nl}
\begin{document}
\makecvtitle
\section{Experience}
\cventry{2023--2024}{Backend Intern}{Fintech BV}{Amsterdam}{}{Built Python APIs}
\section{Skills}
\cvitem{Languages}{Python, Go, SQL}
\end{document}
"""

def test_parse_jake_template():
    c = latexcv.parse_latex(JAKE)
    assert c["name"] == "John Smith" and c["email"] == "john@smith.nl"
    assert any("github.com/jsmith" in l for l in c["links"])
    assert c["order"][:3] == ["education", "experience", "skills"]                 # section order of the source is kept
    assert [len(e["bullets"]) for e in c["experience"]] == [2, 2]
    assert "Delft University" in c["education"][0]["heading"]
    assert {g["label"] for g in c["skill_groups"]} == {"Languages", "Frameworks"}

def test_parse_moderncv_and_flat_text():
    c = latexcv.parse_latex(MODERN)
    assert c["name"] == "Anna Jansen" and c["experience"][0]["bullets"] == ["Built Python APIs"] and "Go" in c["skills"]

def test_tailor_in_place_keeps_template_and_words():
    out, changes = latexcv.tailor_latex(JAKE, ["flutter", "dart", "react"], ["flutter", "dart", "react"])
    assert out != JAKE and changes
    assert out.count(r"\resumeItem{") == JAKE.count(r"\resumeItem{")
    # same multiset of lines -> only re-ordered, nothing added/removed/reworded
    assert sorted(re.findall(r"\w+", out)) == sorted(re.findall(r"\w+", JAKE))
    # the Flutter job comes first inside Experience; Flutter bullet first inside its job; skills reordered
    exp = out[out.index(r"\section{Experience}"):]
    assert exp.index("Shop BV") < exp.index("Bank Corp")
    assert exp.index("Built a \\textbf{Flutter}") < exp.index("Fixed UI bugs")
    assert r"{: Dart, SQL, Java, Python}" in out and r"{: Flutter, React, Django}" in out         # matching skills first
    assert out.startswith(JAKE[:200])                                                # preamble untouched

def test_unsafe_latex_rejected():
    assert latexcv.is_safe(JAKE)
    assert not latexcv.is_safe(r"\documentclass{article}\begin{document}\input{/etc/passwd}\end{document}")
    assert not latexcv.is_safe(r"\immediate\write18{rm -rf /}")
    assert not latexcv.is_safe(r"\usepackage{shellesc}")

def _pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    b = io.BytesIO(); c = canvas.Canvas(b, pagesize=A4); W, H = A4
    def line(y, t, f="Helvetica", s=10, x=50, right=None):
        c.setFont(f, s); c.drawString(x, y, t)
        if right: c.drawRightString(W - 50, y, right)
    line(800, "Jane Doe", "Helvetica-Bold", 20); line(780, "Eindhoven | jane@example.com")
    line(750, "EXPERIENCE", "Helvetica-Bold", 12)
    line(734, "Acme BV", "Helvetica-Bold", 10, right="Jun 2025 - Aug 2025"); line(721, "Mobile Developer Intern", "Helvetica-Oblique", 9)
    line(708, "•  Wrote Python REST APIs", x=60); line(696, "•  Built a Flutter app used by 2000 students", x=60)
    line(670, "SKILLS", "Helvetica-Bold", 12); line(654, "Languages: Dart, Python, SQL")
    c.save(); return b.getvalue()

def test_pdf_to_latex_to_fields_roundtrip():
    r = cv.import_cv(_pdf(), "cv.pdf")
    assert r["source"] == "pdf" and r["cv"]["name"] == "Jane Doe"
    assert r"\entry{Acme BV}{Mobile Developer Intern}{Jun 2025 -- Aug 2025}" in r["latex"]
    assert latexcv.is_safe(r["latex"])
    back = latexcv.parse_latex(r["latex"])
    assert back["name"] == "Jane Doe" and back["experience"][0]["bullets"][-1].startswith("Built a Flutter")
    assert back["order"] == r["cv"]["order"]

def test_tex_upload_is_kept_verbatim():
    r = cv.import_cv(JAKE.encode(), "me.tex")
    assert r["source"] == "latex" and r["latex"] == JAKE and r["cv"]["name"] == "John Smith"

@pytest.mark.skipif(latexcv.compiler() is None, reason="no LaTeX compiler installed")
def test_generated_latex_compiles():
    pdf, err = latexcv.compile_pdf(cv.import_cv(_pdf(), "cv.pdf")["latex"])
    assert pdf and pdf[:4] == b"%PDF", err


def test_pdf_hyperlinks_and_project_meta_survive():
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    b = io.BytesIO(); c = canvas.Canvas(b, pagesize=A4); W, H = A4
    c.setFont("Helvetica-Bold", 20); c.drawString(50, 800, "Jane Doe")
    c.setFont("Helvetica", 10); c.drawString(50, 780, "Eindhoven | jane@example.com")
    c.setFont("Helvetica-Bold", 12); c.drawString(50, 750, "PROJECTS")
    c.setFont("Helvetica-Bold", 10); c.drawString(50, 734, "Shop - Marketplace app")
    c.setFont("Helvetica", 9); c.drawString(200, 734, "Demo"); c.linkURL("https://example.com/demo?x=1", (200, 730, 225, 744))
    c.drawRightString(W - 50, 734, "UAE - 10K+ downloads")
    c.drawString(50, 721, "Buy and sell things online with payments. Stripe, Apple Pay")
    c.save()
    r = cv.import_cv(b.getvalue(), "cv.pdf")
    assert r"\href{https://example.com/demo?x=1}{Demo}" in r["latex"]
    blk = r["cv"]["projects"][0]
    assert blk["links"][0]["url"] == "https://example.com/demo?x=1" and "10K+" in blk["meta"] and blk["title"].startswith("Shop")
