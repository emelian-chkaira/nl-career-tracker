import uuid
from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.orm import Session
from .db import get_db
from .security import decode_access_token
from app.models import User


def bearer(authorization: str | None = Header(None)) -> str | None:
    return authorization[7:] if authorization and authorization.lower().startswith("bearer ") else None


def optional_user(token: str | None = Depends(bearer), db: Session = Depends(get_db)) -> User | None:
    d = decode_access_token(token) if token else None
    if not d: return None
    u = db.get(User, uuid.UUID(d["sub"]))
    return u if u and u.is_active else None


def current_user(u: User | None = Depends(optional_user)) -> User:
    if not u: raise HTTPException(401, "not authenticated", headers={"WWW-Authenticate": "Bearer"})
    return u


def admin_user(u: User = Depends(current_user)) -> User:
    if u.role != "admin": raise HTTPException(403, "admin only")
    return u


def operator_user(u: User = Depends(current_user)) -> User:
    """Crawler controls: any signed-in user when CAREERS_OPEN_CRAWLER is on (the default for self-hosting), otherwise admins only."""
    from .config import settings
    if not settings.open_crawler and u.role != "admin": raise HTTPException(403, "admin only")
    return u


def client_ip(request: Request) -> str:
    from .config import settings
    if settings.trust_proxy and (f := request.headers.get("x-forwarded-for")): return f.split(",")[0].strip()
    return request.client.host if request.client else "?"
