

def test_languages_not_polluted_by_references_and_footer():
    from app.cvtools import cv
    t = ("Jane Doe\nj@x.com\nLANGUAGES\nArabic: native - English: B2 overall, C1 listening - Oxford Placement Test certificate, "
         "Academic reference: Dr. Eva Hreiks, Head of Software Engineering, Al-Baath University - View letter., Jane Doe - Curriculum Vitae - jane.dev\n")
    c = cv.parse_cv(t)
    assert c["languages"] == ["Arabic: native", "English: B2 overall, C1 listening – Oxford Placement Test certificate"]
    assert c["references"][0].startswith("Academic reference: Dr. Eva Hreiks, Head of Software Engineering, Al-Baath University")


def test_ai_tailor_applies_only_safe_edits(monkeypatch):
    import httpx
    from app.cvtools import cv
    c = cv.parse_cv("Jane Doe\nj@x.com\nSKILLS\nPython, Flutter\nEXPERIENCE\n\x01Acme | Dev  2022 - 2024\nplace\n- Built APIs\n- Wrote tests\n")
    reply = {"content": [{"text": '{"summary":"Python dev.","sections":{"experience":[{"i":0,"bullets":["Built Python APIs","Wrote tests"]},{"i":9,"bullets":["x"]}]},"skills_first":["Flutter","Rust"],"gaps":["Kubernetes"],"notes":""}'}]}
    class R:
        def raise_for_status(self): pass
        def json(self): return reply
    monkeypatch.setattr(httpx, "post", lambda *a, **k: R())
    out = cv.ai_tailor(c, {"title": "Python Dev", "company": "X", "description": "python"}, "k")
    assert out["cv"]["experience"][0]["bullets"][0] == "Built Python APIs"
    assert out["cv"]["skills"][0] == "Flutter" and "Rust" not in out["cv"]["skills"]      # unknown skill ignored
    assert out["gaps"] == ["Kubernetes"] and any(x["section"] == "experience" for x in out["changes"])
