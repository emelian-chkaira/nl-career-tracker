"""AI settings, the connected Gmail account (Google OAuth) and the extracted job e-mails (accept / dismiss / edit) of the signed-in user."""
import threading
from fastapi.responses import RedirectResponse
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.deps import current_user
from app.core.netguard import check_url
from app.core.secretbox import seal, unseal
from app.models import User, UserAiSettings, MailAccount, MailEvent, Task, Job, Company
from app.services import llm_service as llm, mail_service as ms, mail_classifier as mc, task_service, gmail_service as gm
from app.core.config import settings

router = APIRouter(prefix="/mail", tags=["mail"])
ai = APIRouter(prefix="/ai", tags=["ai"])


# ------------------------------------------------------------------ AI settings
def cfg_of(db: Session, user: User) -> llm.Cfg:
    s = db.get(UserAiSettings, user.id)
    return llm.Cfg(s.provider, s.model, s.base_url, unseal(s.api_key_enc)) if s else llm.Cfg()


class AiIn(BaseModel):
    provider: str = "rules"
    model: str | None = Field(None, max_length=120)
    base_url: str | None = Field(None, max_length=300)
    api_key: str | None = Field(None, max_length=400)       # omitted/None keeps the saved key; "" removes it


@ai.get("/providers", summary="Every provider preset (editable defaults): free/offline, Chinese models, Claude, OpenAI-compatible…")
def providers(): return [dict(id=k, **v) for k, v in llm.PROVIDERS.items()]


@ai.get("/settings")
def get_ai(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.get(UserAiSettings, user.id)
    return {"provider": s.provider if s else "rules", "model": s.model if s else None, "base_url": s.base_url if s else None, "has_key": bool(s and s.api_key_enc)}


@ai.put("/settings")
def put_ai(body: AiIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.provider not in llm.PROVIDERS: raise HTTPException(400, "unknown provider")
    if body.base_url: check_url(body.base_url)
    s = db.get(UserAiSettings, user.id) or UserAiSettings(user_id=user.id)
    s.provider, s.model, s.base_url = body.provider, (body.model or "").strip() or None, (body.base_url or "").strip() or None
    if body.api_key is not None: s.api_key_enc = seal(body.api_key.strip()) if body.api_key.strip() else None
    db.add(s); db.commit(); return get_ai(user, db)


@ai.post("/test", summary="Check that the saved provider, model and key work")
def test_ai(user: User = Depends(current_user), db: Session = Depends(get_db)):
    cfg = cfg_of(db, user)
    if cfg.base_url: check_url(cfg.base_url)
    try: return llm.test(cfg)
    except llm.LlmError as e: raise HTTPException(502, str(e))


# ------------------------------------------------------------------ mailboxes
def _acc(a: MailAccount) -> dict:
    return {"id": a.id, "provider": a.provider, "label": a.label, "host": a.host, "port": a.port, "username": a.username, "folder": a.folder, "days_back": a.days_back,
            "last_sync_at": a.last_sync_at, "last_error": a.last_error}


def _mine(db: Session, user: User, aid: int) -> MailAccount:
    a = db.get(MailAccount, aid)
    if not a or a.user_id != user.id: raise HTTPException(404, "mailbox not found")
    return a


@router.get("/accounts")
def accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_acc(a) for a in db.scalars(select(MailAccount).where(MailAccount.user_id == user.id).order_by(MailAccount.id))]


@router.delete("/accounts/{aid}", status_code=204, summary="Disconnect: deletes the saved Google token (extracted events stay until you delete them)")
def del_account(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_mine(db, user, aid)); db.commit()


@router.post("/accounts/{aid}/test")
def test_account(aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _mine(db, user, aid)
    try: return gm.test(unseal(a.secret_enc) or "")
    except ms.MailError as e: raise HTTPException(400, str(e))


# ------------------------------------------------------------------ Gmail (Google OAuth, read-only)
@router.get("/gmail/status")
def gmail_status(): return {"configured": gm.configured(), "redirect_uri": gm.redirect_uri(), "scope": "gmail.readonly"}


@router.post("/gmail/start", summary="URL of Google's consent screen; the browser goes there and comes back to /gmail/callback")
def gmail_start(user: User = Depends(current_user)):
    try: return {"url": gm.auth_url(str(user.id))}
    except ms.MailError as e: raise HTTPException(400, str(e))


@router.get("/gmail/callback", include_in_schema=False)
def gmail_callback(code: str = "", state: str = "", error: str = "", db: Session = Depends(get_db)):
    back = settings.api_url.rstrip("/") + "/inbox"
    if error or not code: return RedirectResponse(f"{back}?gmail=denied")
    try:
        import uuid
        uid = uuid.UUID(gm.read_state(state)); got = gm.exchange(code)
    except (ms.MailError, ValueError) as e:
        return RedirectResponse(f"{back}?gmail=error&reason={str(e)[:120]}")
    if not db.get(User, uid): return RedirectResponse(f"{back}?gmail=error")
    a = db.scalar(select(MailAccount).where(MailAccount.user_id == uid, MailAccount.provider == "gmail", MailAccount.username == got["email"]))
    if not a: a = MailAccount(user_id=uid, provider="gmail", label=f"Gmail ({got['email']})", host="gmail.googleapis.com", port=443, username=got["email"], folder="INBOX", days_back=60)
    a.secret_enc, a.last_error = seal(got["refresh_token"]), None
    db.add(a); db.commit(); return RedirectResponse(f"{back}?gmail=connected")


# ------------------------------------------------------------------ sync / import
class SyncIn(BaseModel):
    account_id: int
    days: int | None = Field(None, ge=1, le=365)
    consent: bool = False


def _need_consent(cfg: llm.Cfg, consent: bool):
    if cfg.external and not consent:
        raise HTTPException(400, f"Your e-mails are sent to {llm.PROVIDERS[cfg.provider]['label']} to be analysed. Confirm with consent=true, or choose the built-in rules / a local model.")


def _run_sync(tid: int):
    import logging
    from app.core.db import SessionLocal
    from app.workers import tasks
    with SessionLocal() as db:
        t = db.get(Task, tid)
        try: tasks.mail_sync(t, db); task_service.finish(db, t)
        except Exception as e:
            db.rollback(); logging.getLogger("mail").exception("mail sync failed"); task_service.finish(db, db.get(Task, tid), str(e)[:300])


@router.post("/sync", status_code=202, summary="Read the mailbox in the background and extract job e-mails")
def sync(body: SyncIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _mine(db, user, body.account_id); _need_consent(cfg_of(db, user), body.consent)
    # runs in this process (not the crawler queue), so reading your mailbox never waits behind company scans
    t = Task(kind="mail_sync", status="running", payload={"user_id": str(user.id), "account_id": a.id, "days": body.days or a.days_back}); db.add(t); db.commit()
    threading.Thread(target=_run_sync, args=(t.id,), daemon=True).start(); return {"task_id": t.id}


@router.get("/sync/{tid}")
def sync_status(tid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    t = db.get(Task, tid)
    if not t or t.kind != "mail_sync" or (t.payload or {}).get("user_id") != str(user.id): raise HTTPException(404)
    return {"id": t.id, "status": t.status, "progress": t.progress, "error": t.error}


class ImportIn(BaseModel):
    text: str = Field(min_length=10, max_length=20000)
    subject: str = ""
    sender: str = ""
    consent: bool = False


def _import(db: Session, user: User, mails: list[dict], consent: bool) -> dict:
    cfg = cfg_of(db, user); _need_consent(cfg, consent)
    return mc.process(db, user.id, cfg, mails)


@router.post("/import", summary="Paste one e-mail's text to classify it (no mailbox needed)")
def import_text(body: ImportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    import hashlib
    m = {"message_id": "paste-" + hashlib.sha1((body.subject + body.text).encode()).hexdigest()[:20], "sender": body.sender, "sender_addr": body.sender.lower().split("<")[-1].strip(">"),
         "subject": body.subject, "date": None, "body": body.text[:ms.MAX_BODY]}
    return _import(db, user, [m], body.consent)


@router.post("/import-eml", summary="Upload .eml files exported from any mail app")
async def import_eml(files: list[UploadFile] = File(...), consent: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if len(files) > 50: raise HTTPException(400, "at most 50 files at a time")
    mails = [ms.parse_eml((await f.read())[:2_000_000]) for f in files]
    return _import(db, user, mails, consent)


# ------------------------------------------------------------------ events: review inbox
def _ev(e: MailEvent, jobs: dict, companies: dict) -> dict:
    j = jobs.get(e.job_id)
    return {"id": e.id, "category": e.category, "company": e.company, "role": e.role, "location": e.location, "event_date": e.event_date, "summary": e.summary, "subject": e.subject,
            "sender": e.sender, "received_at": e.received_at, "confidence": e.confidence, "classifier": e.classifier, "status": e.status,
            "company_id": e.company_id, "company_known": companies.get(e.company_id), "job_id": e.job_id, "job": j,
            "suggested_stage": mc.STAGE_OF.get(e.category)}


@router.get("/events")
def events(status: str | None = None, category: str | None = None, q: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = [MailEvent.user_id == user.id]
    if status: w.append(MailEvent.status == status)
    if category: w.append(MailEvent.category == category)
    if q: w.append((MailEvent.company.ilike(f"%{q}%")) | (MailEvent.role.ilike(f"%{q}%")) | (MailEvent.subject.ilike(f"%{q}%")))
    rows = db.scalars(select(MailEvent).where(*w).order_by(MailEvent.received_at.desc().nullslast(), MailEvent.id.desc()).limit(500)).all()
    jobs = {j.id: {"id": j.id, "title": j.title} for j in db.scalars(select(Job).where(Job.id.in_([r.job_id for r in rows if r.job_id])))} if rows else {}
    comps = {c.id: c.name for c in db.scalars(select(Company).where(Company.id.in_([r.company_id for r in rows if r.company_id])))} if rows else {}
    counts = {"category": {c: n for c, n in db.execute(select(MailEvent.category, func.count()).where(MailEvent.user_id == user.id).group_by(MailEvent.category))},
              "status": {c: n for c, n in db.execute(select(MailEvent.status, func.count()).where(MailEvent.user_id == user.id).group_by(MailEvent.status))}}
    return {"items": [_ev(e, jobs, comps) for e in rows], "counts": counts}


class EventPatch(BaseModel):
    category: str | None = None
    company: str | None = Field(None, max_length=200)
    role: str | None = Field(None, max_length=250)
    job_id: int | None = None
    unlink_job: bool = False


def _event(db: Session, user: User, eid: int) -> MailEvent:
    e = db.get(MailEvent, eid)
    if not e or e.user_id != user.id: raise HTTPException(404)
    return e


@router.patch("/events/{eid}", summary="Correct what the classifier got wrong")
def patch_event(eid: int, body: EventPatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _event(db, user, eid)
    if body.category:
        if body.category not in mc.CATEGORIES: raise HTTPException(400, "unknown category")
        e.category = body.category
    if body.company is not None: e.company = body.company or None
    if body.role is not None: e.role = body.role or None
    if body.unlink_job: e.job_id = None
    elif body.job_id: 
        if not db.get(Job, body.job_id): raise HTTPException(404, "job not found")
        e.job_id = body.job_id
    db.commit(); return {"ok": True}


def _accept(db: Session, user: User, e: MailEvent) -> str | None:
    stage = mc.apply_stage(db, user.id, e); e.status = "accepted"; return stage


@router.post("/events/{eid}/accept", summary="Keep it, and move the linked job in your pipeline (applied / interview / offer / rejected)")
def accept(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _event(db, user, eid); stage = _accept(db, user, e); db.commit(); return {"ok": True, "stage": stage}


@router.post("/events/{eid}/dismiss")
def dismiss(eid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    e = _event(db, user, eid); e.status = "dismissed"; db.commit(); return {"ok": True}


class Bulk(BaseModel):
    ids: list[int] = Field(max_length=500)
    action: str                       # accept | dismiss | delete


@router.post("/events/bulk")
def bulk(body: Bulk, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if body.action not in ("accept", "dismiss", "delete"): raise HTTPException(400, "action must be accept, dismiss or delete")
    n = 0
    for e in db.scalars(select(MailEvent).where(MailEvent.user_id == user.id, MailEvent.id.in_(body.ids))):
        if body.action == "accept": _accept(db, user, e)
        elif body.action == "dismiss": e.status = "dismissed"
        else: db.delete(e)
        n += 1
    db.commit(); return {"changed": n}


@router.delete("/events", status_code=204, summary="Delete everything extracted from your e-mails")
def delete_events(user: User = Depends(current_user), db: Session = Depends(get_db)):
    from sqlalchemy import delete
    db.execute(delete(MailEvent).where(MailEvent.user_id == user.id)); db.commit()
