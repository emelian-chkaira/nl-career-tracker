from app.cvtools import cv

SAMPLE = """Jane Doe
Eindhoven, Netherlands | jane.doe@example.com | +31 6 12345678 | github.com/janedoe

Profile
Computer science student who likes building mobile apps.

Skills
Languages: Dart, Python, SQL
Tools: Flutter, Docker, Git

Experience
Mobile Developer Intern - Acme BV  Jun 2025 - Aug 2025
- Built a Flutter app used by 2,000 students
- Wrote REST integrations with Python backend
- Organised weekly team lunches

Education
BSc Computer Science, TU/e  2022 - 2026
- Thesis on cross-platform mobile frameworks

Projects
Habit Tracker
- Flutter + Firebase app with offline sync
"""

def test_parse_basic_fields():
    c = cv.parse_cv(SAMPLE)
    assert c["name"] == "Jane Doe" and c["email"] == "jane.doe@example.com" and c["location"].startswith("Eindhoven")
    assert any("github.com/janedoe" in l for l in c["links"])
    low = [s.lower() for s in c["skills"]]
    assert "flutter" in low and "dart" in low and "docker" in low
    assert len(c["experience"]) == 1 and len(c["experience"][0]["bullets"]) == 3
    assert c["education"] and c["projects"]

def test_tailor_reorders_without_inventing():
    c = cv.parse_cv(SAMPLE)
    job = dict(title="Flutter Developer Intern", description="We need Flutter, Dart, Firebase and Kotlin experience. REST APIs a plus.", job_type="internship")
    t = cv.tailor(c, job, "Acme")
    assert "flutter" in t["matched"] and "kotlin" in t["gaps"]
    assert "kotlin" not in [s.lower() for s in t["cv"]["skills"]]            # gaps are never added to the CV
    assert t["cv"]["skills"][0].lower() in ("flutter", "dart")                 # matching skills first
    assert t["cv"]["experience"][0]["bullets"][0].startswith("Built a Flutter")
    assert t["cv"]["order"][0] == "education"                                   # internships lead with education
    assert "Flutter Developer Intern" in t["cv"]["summary"]
    assert "<h1>Jane Doe</h1>" in cv.render_html(t["cv"]) and "JANE DOE" in cv.render_text(t["cv"])

def test_cover_letter_uses_only_cv_facts():
    c = cv.parse_cv(SAMPLE)
    job = dict(title="Flutter Developer Intern", description="Flutter and Dart app development.", job_type="internship")
    out = cv.cover_letter(c, job, {"name": "Acme", "description": "Acme builds learning apps for students. More text follows here."})
    assert "Acme" in out["text"] and "Flutter" in out["text"] and "Jane Doe" in out["text"]
    assert "Acme builds learning apps for students." in out["text"]
    assert out["placeholders"] >= 1                                              # motivation sentence left for the user

def test_docx_and_text_extraction():
    import io, zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z: z.writestr("word/document.xml", "<w:document><w:p><w:r><w:t>Jane Doe</w:t></w:r></w:p><w:p><w:r><w:t>Skills</w:t></w:r></w:p></w:document>")
    assert cv.extract_text(b.getvalue(), "cv.docx") == "Jane Doe\nSkills"
    assert cv.extract_text("Hello – world".encode(), "cv.txt").startswith("Hello")

def test_phone_not_confused_with_date_range():
    c = cv.parse_cv("Jane Doe\njane@example.com\n\nExperience\nIntern - Acme  2025 - 2026\n- did things\n")
    assert c["phone"] == ""
    assert cv.parse_cv("Jane Doe\n+31 6 1234 5678\n")["phone"].startswith("+31")
