"""Password hashing (argon2id), JWT access tokens, opaque rotating refresh tokens."""
import hashlib, secrets, uuid, datetime as dt
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError
from .config import settings

_ph = PasswordHasher()
ALGO = "HS256"


def hash_password(pw: str) -> str: return _ph.hash(pw)
def verify_password(pw: str, hashed: str) -> bool:
    try: return _ph.verify(hashed, pw)
    except (VerifyMismatchError, InvalidHashError): return False


def create_access_token(user_id: uuid.UUID, role: str) -> str:
    now = dt.datetime.now(dt.timezone.utc)
    return jwt.encode({"sub": str(user_id), "role": role, "iat": now, "exp": now + dt.timedelta(minutes=settings.access_ttl_min), "typ": "access"}, settings.jwt_secret, algorithm=ALGO)


def decode_access_token(token: str) -> dict | None:
    try:
        d = jwt.decode(token, settings.jwt_secret, algorithms=[ALGO])
        return d if d.get("typ") == "access" else None
    except jwt.PyJWTError: return None


def new_refresh_token() -> tuple[str, str]:
    """-> (token to give the client, sha256 hash to store)"""
    t = secrets.token_urlsafe(48)
    return t, hashlib.sha256(t.encode()).hexdigest()


def hash_refresh(token: str) -> str: return hashlib.sha256(token.encode()).hexdigest()
