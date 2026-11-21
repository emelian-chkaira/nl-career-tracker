"""Encrypt small secrets (users' API keys, the Gmail refresh token) before they are stored. Key = derived from CAREERS_JWT_SECRET,
so rotating that secret makes saved keys unreadable (users simply re-enter them)."""
import base64, hashlib
from cryptography.fernet import Fernet, InvalidToken
from .config import settings


def _f() -> Fernet: return Fernet(base64.urlsafe_b64encode(hashlib.sha256(("secretbox:" + settings.jwt_secret).encode()).digest()))
def seal(plain: str | None) -> str | None: return _f().encrypt(plain.encode()).decode() if plain else None
def unseal(token: str | None) -> str | None:
    if not token: return None
    try: return _f().decrypt(token.encode()).decode()
    except InvalidToken: return None
