from fastapi import APIRouter, Depends, Request, Response, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.db import get_db
from app.core.deps import current_user, client_ip
from app.core import ratelimit, security
from app.models import User
from app.schemas.auth import RegisterIn, LoginIn, RefreshIn, TokenOut, UserOut, ProfileIn, PasswordChangeIn, EmailIn, TokenIn, ResetIn, GoogleIn
from app.services import auth_service as svc, account_service as acct, alert_service, google_service, firebase_service as fb

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "refresh_token"


def _limit(request: Request):
    if not ratelimit.allow("auth:" + client_ip(request), settings.auth_rate_limit_per_min): raise HTTPException(429, "too many attempts, slow down")


def _flush_mail():
    from app.core.db import SessionLocal
    with SessionLocal() as s: alert_service.send_outbox(s)


def _respond(response: Response, user: User, access: str, refresh: str) -> TokenOut:
    response.set_cookie(COOKIE, refresh, httponly=True, secure=settings.cookie_secure, samesite="lax", max_age=settings.refresh_ttl_days * 86400, path="/api/v1/auth")
    return TokenOut(access_token=access, refresh_token=refresh, expires_in=settings.access_ttl_min * 60, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenOut, status_code=201)
def register(body: RegisterIn, request: Request, response: Response, bg: BackgroundTasks, db: Session = Depends(get_db)):
    _limit(request)
    if settings.firebase_on: u = fb.register(db, body.email, body.password, body.name)
    else: u = svc.register(db, body.email, body.password, body.name); acct.send_verification(db, u); bg.add_task(_flush_mail)
    access, refresh = svc.issue_tokens(db, u)
    return _respond(response, u, access, refresh)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _limit(request)
    u = fb.login(db, body.email, body.password) if settings.firebase_on else svc.authenticate(db, body.email, body.password)
    access, refresh = svc.issue_tokens(db, u)
    return _respond(response, u, access, refresh)


@router.post("/refresh", response_model=TokenOut)
def refresh(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    _limit(request)
    raw = (body.refresh_token if body else None) or request.cookies.get(COOKIE)
    if not raw: raise HTTPException(401, "no refresh token")
    u, access, new = svc.rotate(db, raw)
    return _respond(response, u, access, new)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, body: RefreshIn | None = None, db: Session = Depends(get_db)):
    svc.revoke(db, (body.refresh_token if body else None) or request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/api/v1/auth")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)): return user


@router.put("/profile", response_model=UserOut)
def update_profile(body: ProfileIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.profile = body.model_dump(); db.commit(); return user


@router.post("/password", status_code=204)
def change_password(body: PasswordChangeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if settings.firebase_on: fb.change_password(user, body.current_password, body.new_password); return
    if not security.verify_password(body.current_password, user.password_hash): raise HTTPException(400, "current password is wrong")
    user.password_hash = security.hash_password(body.new_password); db.commit()


@router.post("/verify/send", status_code=202)
def resend_verification(request: Request, bg: BackgroundTasks, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _limit(request)
    if settings.firebase_on: fb.resend_verification(db, user)
    else: acct.send_verification(db, user); bg.add_task(_flush_mail)
    return {"sent": not user.email_verified}


@router.post("/verify", response_model=UserOut)
def verify_email(body: TokenIn, request: Request, db: Session = Depends(get_db)):
    _limit(request); return fb.verify(db, body.token) if settings.firebase_on else acct.verify(db, body.token)


@router.post("/forgot", status_code=202)
def forgot_password(body: EmailIn, request: Request, bg: BackgroundTasks, db: Session = Depends(get_db)):
    _limit(request)
    if settings.firebase_on: fb.forgot(body.email)
    else: acct.send_reset(db, body.email); bg.add_task(_flush_mail)
    return {"ok": True}                    # identical answer whether or not the account exists


@router.post("/reset", status_code=204)
def reset_password(body: ResetIn, request: Request, db: Session = Depends(get_db)):
    _limit(request); fb.reset(db, body.token, body.new_password) if settings.firebase_on else acct.reset(db, body.token, body.new_password)


@router.get("/config")
def auth_config(): return {"google_client_id": (settings.google_ids or [None])[0], "provider": "firebase" if settings.firebase_on else "local"}


@router.post("/google", response_model=TokenOut)
def google_login(body: GoogleIn, request: Request, response: Response, db: Session = Depends(get_db)):
    _limit(request)
    u = fb.google(db, body.credential) if settings.firebase_on else google_service.sign_in(db, body.credential)
    access, refresh = svc.issue_tokens(db, u)
    return _respond(response, u, access, refresh)
