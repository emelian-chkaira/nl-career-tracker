"""CV tools — stateless: nothing is stored server-side; the client keeps the CV and sends it with each request."""
import base64
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select
from app.core import ratelimit
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import client_ip
from app.cvtools import cv as cvmod, latexcv
from app.models import Job

router = APIRouter(prefix="/cv", tags=["cv"])


def guard(request: Request):
    if not ratelimit.allow("cv:" + client_ip(request), 30): raise HTTPException(429, "too many CV requests, try again in a minute")


class CvReq(BaseModel):
    cv: dict
    job_id: int
    tone: str = "professional"
    extra: str = ""
    ai: bool = False
    latex: str = ""
    compile: bool = False


def _job(db: Session, jid: int) -> dict:
    j = db.scalar(select(Job).where(Job.id == jid).options(selectinload(Job.company)))
    if not j: raise HTTPException(404, "job not found")
    if len(j.description or "") < 200:
        from app.crawler import discovery
        try:
            d = discovery.fetch_detail(j.url)
            if d.get("description"): j.description = d["description"]; db.commit()
        except Exception: db.rollback()
    return {"id": j.id, "title": j.title, "description": j.description or "", "job_type": j.job_type, "location": j.location, "url": j.url, "company": j.company.name, "cdesc": j.company.description}


@router.post("/extract", dependencies=[Depends(guard)], summary="PDF/DOCX/text/LaTeX -> structured CV + LaTeX source")
async def extract(request: Request, filename: str = ""):
    data = await request.body()
    if not data: raise HTTPException(400, "empty file")
    try: return cvmod.import_cv(data, filename)
    except Exception as e: raise HTTPException(400, f"could not read the file: {str(e)[:140]}")


@router.post("/parse", dependencies=[Depends(guard)])
def parse(body: dict):
    if body.get("latex"):
        src = str(body["latex"])[:200000]
        if not latexcv.is_safe(src): raise HTTPException(400, "LaTeX contains disallowed commands")
        return {"cv": latexcv.parse_latex(src), "latex": src, "source": "latex"}
    c = cvmod.parse_cv(str(body.get("text", ""))[:60000])
    return {"cv": c, "latex": latexcv.to_latex(c), "source": "text"}


class PdfReq(BaseModel):
    latex: str = ""
    cv: dict | None = None
    mode: str = "auto"            # local | public | auto
    allow_public: bool = False    # explicit consent: the document is sent to a third-party LaTeX service


class AiReq(BaseModel):
    cv: dict
    job_id: int
    consent: bool = False         # explicit: the CV and the posting are sent to Anthropic


@router.post("/ai-tailor", dependencies=[Depends(guard)], summary="LLM rewrite of the CV for one job (opt-in, no invented facts)")
def ai_tailor(req: AiReq, db: Session = Depends(get_db)):
    if not settings.anthropic_api_key: raise HTTPException(400, "AI tailoring is not enabled on this server (set ANTHROPIC_API_KEY)")
    if not req.consent: raise HTTPException(400, "AI tailoring sends your CV to Anthropic; consent=true is required")
    j = _job(db, req.job_id)
    try: r = cvmod.ai_tailor(req.cv, j, settings.anthropic_api_key)
    except Exception as e: raise HTTPException(502, f"AI tailoring failed: {str(e)[:120]}")
    r["latex"] = latexcv.to_latex(r["cv"])
    r["job"] = {"title": j["title"], "company": j["company"]}
    return r


@router.get("/compilers", summary="Which LaTeX compilers can build a PDF")
def compilers():
    return {"local": bool(latexcv.compiler()), "local_name": (latexcv.compiler() or "").split("/")[-1], "public": list(latexcv.PUBLIC_SERVICES), "ai": bool(settings.anthropic_api_key)}


@router.post("/pdf", dependencies=[Depends(guard)], summary="LaTeX (or structured CV) -> PDF, locally or via a public LaTeX service (opt-in)")
def pdf(req: PdfReq):
    src = (req.latex or (latexcv.to_latex(req.cv) if req.cv else ""))[:200000]
    if not src.strip(): raise HTTPException(400, "nothing to compile")
    if not latexcv.is_safe(src): raise HTTPException(400, "LaTeX contains disallowed commands")
    mode = req.mode if req.mode in ("local", "public", "auto") else "auto"
    if mode == "public" and not req.allow_public: raise HTTPException(400, "sending the CV to a public LaTeX service needs allow_public=true")
    r = latexcv.compile_any(src, mode)
    if not r["pdf"]: raise HTTPException(422, {"error": r["error"] or "compilation failed", "local_available": r["local_available"], "latex": src})
    return {"pdf_b64": base64.b64encode(r["pdf"]).decode(), "engine": r["engine"], "bytes": len(r["pdf"])}


@router.post("/latex", dependencies=[Depends(guard)])
def latex(body: dict): return {"latex": latexcv.to_latex(body.get("cv") or {})}


def _key(req: CvReq):
    if not req.ai: return None
    if not settings.anthropic_api_key: raise HTTPException(400, "AI polish is not enabled on this server")
    return settings.anthropic_api_key


@router.post("/tailor", dependencies=[Depends(guard)])
def tailor(req: CvReq, db: Session = Depends(get_db)):
    key = _key(req); j = _job(db, req.job_id)
    t = cvmod.tailor(req.cv, j, j["company"]); text = cvmod.render_text(t["cv"])
    if key:
        try: text = cvmod.polish("CV (plain text)", cvmod.render_text(req.cv), j, text, key)
        except Exception as e: raise HTTPException(502, f"AI polish failed: {str(e)[:100]}")
    t.update(text=text, html=cvmod.render_html(t["cv"]), ai=bool(key))
    src = req.latex[:200000]
    if src:
        if not latexcv.is_safe(src): raise HTTPException(400, "LaTeX contains disallowed commands")
        t["latex"], t["changes"] = latexcv.tailor_latex(src, t["keywords"], t["matched"])
        if req.compile:
            pdf, err = latexcv.compile_pdf(t["latex"])
            t["pdf_b64"] = base64.b64encode(pdf).decode() if pdf else None; t["pdf_error"] = err
    return t


@router.post("/cover-letter", dependencies=[Depends(guard)])
def cover(req: CvReq, db: Session = Depends(get_db)):
    key = _key(req); j = _job(db, req.job_id)
    out = cvmod.cover_letter(req.cv, j, {"name": j["company"], "description": j["cdesc"]}, req.tone, req.extra)
    if key:
        try: out["text"] = cvmod.polish("cover letter", cvmod.render_text(req.cv), j, out["text"], key)
        except Exception as e: raise HTTPException(502, f"AI polish failed: {str(e)[:100]}")
    out.update(ai=bool(key), job={"title": j["title"], "company": j["company"], "url": j["url"]}); return out
