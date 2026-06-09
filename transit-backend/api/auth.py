"""
Authentication Utilities
--------------------------
Password hashing, JWT creation/validation, and the FastAPI dependency
that protects routes requiring a logged-in user.
"""
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt as _bcrypt
from jose import JWTError, jwt

from db.database import get_connection

# ── Config (override via .env) ────────────────────────────────────────────
JWT_SECRET = os.getenv(
    "JWT_SECRET",
    "change-me-in-production-use-a-long-random-secret-min-32-chars",
)
# Enforce strong JWT secret in production
if os.getenv("ENV") == "production" and JWT_SECRET.startswith("change-me"):
    raise RuntimeError("[SECURITY] JWT_SECRET must be set to a strong value in production!")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "720"))  # 30 days

# Unique ID for this server process. Tokens issued by a previous process
# (i.e. before a server restart) are rejected with 401, forcing re-login.
_SERVER_INSTANCE_ID: str = str(uuid.uuid4())

# ── Password hashing ──────────────────────────────────────────────────────
# passlib 1.7.4 is incompatible with bcrypt >=4. We use bcrypt directly.
# Pre-hashing with SHA-256 produces exactly 32 bytes — well under bcrypt's
# 72-byte limit — so the ValueError is impossible.

def _prehash(plain: str) -> bytes:
    """Return the raw 32-byte SHA-256 digest of the password."""
    return hashlib.sha256(plain.encode("utf-8")).digest()


def hash_password(plain: str) -> str:
    salt = _bcrypt.gensalt()
    return _bcrypt.hashpw(_prehash(plain), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(_prehash(plain), hashed.encode("utf-8"))


# ── JWT helpers ───────────────────────────────────────────────────────────

def create_access_token(user_id: str, email: str) -> str:
    """Create a signed JWT for the given user."""
    expire = datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS)
    payload = {
        "sub": user_id,
        "email": email,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "sid": _SERVER_INSTANCE_ID,  # invalidated on server restart
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Decode and verify a JWT. Returns {} on any failure."""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        return {}


def create_state_token() -> str:
    """Create a short-lived signed state token for OAuth CSRF protection."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=10)
    payload = {"nonce": secrets.token_urlsafe(16), "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_state_token(state: str) -> bool:
    """Return True if the state token is valid and not expired."""
    try:
        jwt.decode(state, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return True
    except JWTError:
        return False


# ── Password reset tokens ─────────────────────────────────────────────────

def generate_reset_token() -> tuple[str, str]:
    """
    Generate a password reset token.
    Returns (plain_token, token_hash).
    Store the hash in the DB; send the plain token to the user.
    """
    plain = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(plain.encode()).hexdigest()
    return plain, hashed


def hash_reset_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


# ── FastAPI dependency ────────────────────────────────────────────────────
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict:
    """
    Decode the Bearer JWT and return the user dict.
    Raises HTTP 401 if the token is missing, invalid, or the user no longer exists.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    user_id: Optional[str] = payload.get("sub")

    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject tokens issued before the current server boot (server restart guard)
    if payload.get("sid") != _SERVER_INSTANCE_ID:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, email, display_name FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return {"id": row["id"], "email": row["email"], "display_name": row["display_name"]}
