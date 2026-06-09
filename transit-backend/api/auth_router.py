"""
Auth Router
------------
Endpoints for account creation, sign-in, password reset, and OAuth (Google / Facebook).

Routes:
  POST  /auth/signup               — create account with email + password
  POST  /auth/login                — sign in with email + password
  POST  /auth/forgot-password      — request password-reset email
  POST  /auth/reset-password       — complete password reset with token
  GET   /auth/me                   — return current user (requires JWT)
  PUT   /auth/display-name         — update the authenticated user's display name
  GET   /auth/google/login         — start Google OAuth2 flow (opens in popup)
  GET   /auth/google/callback      — Google OAuth2 callback
  GET   /auth/facebook/login       — start Facebook OAuth2 flow (opens in popup)
  GET   /auth/facebook/callback    — Facebook OAuth2 callback
"""
import logging
import os
import re
import smtplib
import time
import uuid
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, EmailStr, Field, field_validator

from api.auth import (
    create_access_token,
    create_state_token,
    generate_reset_token,
    get_current_user,
    hash_password,
    hash_reset_token,
    verify_password,
    verify_state_token,
)
from db.database import get_connection


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

# Simple in-memory rate limiter (per IP, per endpoint)
_RATE_LIMIT = {}
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX = 10    # max attempts per window

def _rate_limit(request: Request, key: str):
    ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    bucket = _RATE_LIMIT.setdefault((ip, key), [])
    # Remove old timestamps
    bucket[:] = [t for t in bucket if now - t < _RATE_LIMIT_WINDOW]
    if len(bucket) >= _RATE_LIMIT_MAX:
        logger.warning(f"Rate limit exceeded for {ip} on {key}")
        raise HTTPException(status_code=429, detail="Too many attempts, try again later.")
    bucket.append(now)

# ── Environment config ────────────────────────────────────────────────────
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:8000")

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = f"{APP_BASE_URL}/auth/google/callback"



SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM     = os.getenv("SMTP_FROM", "")

RESET_TOKEN_EXPIRE_HOURS    = int(os.getenv("RESET_TOKEN_EXPIRE_HOURS", "1"))
RESET_RESEND_COOLDOWN_SECS  = int(os.getenv("RESET_RESEND_COOLDOWN_MINUTES", "5")) * 60

# ── Password complexity helper ────────────────────────────────────────────

_SPECIAL_CHARS = re.compile(r'[!@#$%^&*()\-_=+\[\]{};:\'",./<>?\\|~`]')


def _check_password_complexity(v: str) -> str:
    """Raise ValueError if password does not meet complexity rules."""
    if not re.search(r'[A-Z]', v):
        raise ValueError('Password must contain at least one uppercase letter.')
    if not re.search(r'\d', v):
        raise ValueError('Password must contain at least one number.')
    if not _SPECIAL_CHARS.search(v):
        raise ValueError(
            "Password must contain at least one special character "
            "(e.g. !@#$%^&*()-_=+[]{};\\'\",./<>?|~`)."
        )
    return v


# ============================================================
# Shared helpers
# ============================================================

def _get_or_create_oauth_user(
    email: str, display_name: str, provider: str, provider_id: str
) -> dict:
    """
    Look up an existing user by provider ID, then by email (account linking),
    or create a new one. Returns a plain user dict.
    """
    conn = get_connection()
    try:
        # 1. Exact provider match
        row = conn.execute(
            "SELECT id, email, display_name FROM users "
            "WHERE auth_provider = ? AND provider_id = ?",
            (provider, provider_id),
        ).fetchone()
        if row:
            return dict(row)

        # 2. Existing email — link the provider to the account
        row = conn.execute(
            "SELECT id, email, display_name FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET auth_provider = ?, provider_id = ?, "
                "is_verified = 1, updated_at = ? WHERE id = ?",
                (provider, provider_id, int(time.time()), row["id"]),
            )
            conn.commit()
            return dict(row)

        # 3. New user
        user_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO users (id, email, display_name, auth_provider, provider_id, is_verified) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (user_id, email, display_name, provider, provider_id),
        )
        conn.commit()
        return {"id": user_id, "email": email, "display_name": display_name}
    finally:
        conn.close()


def _oauth_success_page(token: str) -> str:
    """HTML page that posts the JWT to the opener window and closes itself."""
    return f"""<!DOCTYPE html>
<html>
<head><title>Signing in…</title></head>
<body>
<script>
  try {{
    if (window.opener && window.opener.location.origin === window.location.origin) {{
      window.opener.postMessage({{ type: 'oauth_success', token: {repr(token)} }}, window.location.origin);
    }}
  }} catch (e) {{}}
  window.close();
</script>
<p style="font-family:sans-serif;text-align:center;margin-top:40px">
  Signing in&hellip; this window will close automatically.
</p>
</body>
</html>"""


def _oauth_error_page(message: str) -> str:
    """HTML page that posts an error to the opener window and closes itself."""
    import html as _html
    safe_msg = _html.escape(message)
    return f"""<!DOCTYPE html>
<html>
<head><title>Sign-in error</title></head>
<body>
<script>
  try {{
    if (window.opener && window.opener.location.origin === window.location.origin) {{
      window.opener.postMessage({{ type: 'oauth_error', message: {repr(message)} }}, window.location.origin);
    }}
  }} catch (e) {{}}
  window.close();
</script>
<p style="font-family:sans-serif;text-align:center;margin-top:40px;color:#c00">
  Sign-in failed: {safe_msg}.<br>You can close this window and try again.
</p>
</body>
</html>"""


def _send_reset_email(to_email: str, reset_link: str) -> None:
    """
    Send a password-reset email via Gmail SMTP (TLS on port 587).
    Falls back to logging the link when SMTP credentials are not configured
    (useful for local development).
    """
    _from = SMTP_FROM or SMTP_USER  # SMTP_FROM defaults to SMTP_USER if blank

    if not SMTP_USER or not SMTP_PASSWORD:
        logger.info(
            "[auth] SMTP not configured — password reset link for %s: %s",
            to_email,
            reset_link,
        )
        return

    # ── Plain-text body ───────────────────────────────────────────────────
    plain_body = (
        f"Hi,\n\n"
        f"We received a request to reset your Commute Assistant password.\n\n"
        f"Click the link below to set a new password "
        f"(valid for {RESET_TOKEN_EXPIRE_HOURS} hour(s)):\n\n"
        f"{reset_link}\n\n"
        f"This link expires in {RESET_TOKEN_EXPIRE_HOURS} hour(s). "
        f"If you didn't request this, you can safely ignore this email \u2014 "
        f"your password will not be changed.\n\n"
        f"\u2014 Commute Assistant Team"
    )

    # ── HTML body ─────────────────────────────────────────────────────────
    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;padding:24px;color:#222">
  <div style="text-align:center;margin-bottom:24px">
    <span style="font-size:36px">&#128652;</span>
    <h2 style="margin:8px 0 4px">Commute Assistant</h2>
    <p style="color:#666;margin:0">Password Reset</p>
  </div>
  <p>Hi,</p>
  <p>We received a request to reset your password. Click the button below to choose a new one.</p>
  <p style="text-align:center;margin:32px 0">
    <a href="{reset_link}"
       style="background:#10a37f;color:#fff;text-decoration:none;padding:12px 28px;
              border-radius:8px;font-weight:bold;display:inline-block">
      Reset My Password
    </a>
  </p>
  <p style="font-size:13px;color:#666">
    This link expires in <strong>{RESET_TOKEN_EXPIRE_HOURS} hour(s)</strong>.
    If you didn't request a password reset, you can safely ignore this email.
  </p>
  <hr style="border:none;border-top:1px solid #eee;margin:24px 0">
  <p style="font-size:12px;color:#aaa;text-align:center">
    Commute Assistant &mdash; Durham Region Transit AI Helper
  </p>
</body>
</html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your Commute Assistant password"
    msg["From"]    = _from
    msg["To"]      = to_email
    msg.attach(MIMEText(plain_body, "plain"))
    msg.attach(MIMEText(html_body,  "html"))   # HTML part shown by most clients

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(_from, [to_email], msg.as_string())
        logger.info("[auth] Password reset email sent to %s", to_email)
    except smtplib.SMTPAuthenticationError:
        logger.error(
            "[auth] Gmail SMTP authentication failed. "
            "Check SMTP_USER / SMTP_PASSWORD (use an App Password, not your Gmail password)."
        )
    except Exception as exc:
        logger.error("[auth] Failed to send reset email to %s: %s", to_email, exc)


# ============================================================
# POST /auth/signup
# ============================================================

class SignupRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., min_length=8, max_length=32)
    display_name: str = Field(default="", max_length=100)

    @field_validator('password')
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _check_password_complexity(v)


class AuthResponse(BaseModel):
    token: str
    user: dict


@router.post("/signup", response_model=AuthResponse, summary="Create a new account")
def signup(body: SignupRequest, request: Request):
    _rate_limit(request, "signup")
    conn = get_connection()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE email = ?", (body.email,)
        ).fetchone()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An account with this email already exists.",
            )

        user_id = str(uuid.uuid4())
        pw_hash = hash_password(body.password)
        display = body.display_name.strip() or body.email.split("@")[0]

        try:
            conn.execute("BEGIN")
            conn.execute(
                "INSERT INTO users (id, email, password_hash, display_name, auth_provider, is_verified) "
                "VALUES (?, ?, ?, ?, 'local', 0)",
                (user_id, body.email, pw_hash, display),
            )
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Signup DB error: {e}")
            raise HTTPException(status_code=500, detail="Failed to create account.")
    finally:
        conn.close()

    token = create_access_token(user_id=user_id, email=body.email)
    return AuthResponse(
        token=token,
        user={"id": user_id, "email": body.email, "display_name": display},
    )


# ============================================================
# POST /auth/login
# ============================================================

class LoginRequest(BaseModel):
    email: EmailStr = Field(..., max_length=254)
    password: str = Field(..., min_length=1, max_length=32)


@router.post("/login", response_model=AuthResponse, summary="Sign in with email and password")
def login(body: LoginRequest, request: Request):
    _rate_limit(request, "login")
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, email, password_hash, display_name, auth_provider "
            "FROM users WHERE email = ?",
            (body.email,),
        ).fetchone()
    finally:
        conn.close()

    # Prevent email enumeration: always hash even when user is not found
    _invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
    )

    if not row:
        hash_password("timing-attack-prevention-dummy")
        raise _invalid

    if row["auth_provider"] != "local" or not row["password_hash"]:
        # Always return generic error for login to avoid leaking info
        raise _invalid

    if not verify_password(body.password, row["password_hash"]):
        raise _invalid

    token = create_access_token(user_id=row["id"], email=row["email"])
    return AuthResponse(
        token=token,
        user={"id": row["id"], "email": row["email"], "display_name": row["display_name"]},
    )


# ============================================================
# POST /auth/forgot-password
# ============================================================

class ForgotPasswordRequest(BaseModel):
    email: EmailStr


@router.post("/forgot-password", summary="Request a password-reset email")
def forgot_password(body: ForgotPasswordRequest):
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, auth_provider FROM users WHERE email = ?", (body.email,)
        ).fetchone()
    finally:
        conn.close()

    # Always return the same message to prevent email enumeration
    _ok = {"message": "If that email is registered, you'll receive a reset link shortly."}

    if not row or row["auth_provider"] != "local":
        return _ok

    now = int(time.time())

    # ── Cooldown check: if a valid, unused, non-expired token was issued
    # recently (within RESET_RESEND_COOLDOWN_SECS), silently return OK.
    # This prevents attackers from flooding a victim's inbox.
    conn = get_connection()
    try:
        recent = conn.execute(
            "SELECT created_at FROM password_reset_tokens "
            "WHERE user_id = ? AND used = 0 AND expires_at > ? "
            "ORDER BY created_at DESC LIMIT 1",
            (row["id"], now),
        ).fetchone()
    finally:
        conn.close()

    if recent and (now - recent["created_at"]) < RESET_RESEND_COOLDOWN_SECS:
        # A valid reset email was sent very recently — do not re-send
        logger.info(
            "[auth] Reset email for %s suppressed (cooldown active, sent %ds ago)",
            body.email,
            now - recent["created_at"],
        )
        return _ok

    plain_token, token_hash = generate_reset_token()
    expires_at = now + RESET_TOKEN_EXPIRE_HOURS * 3600

    conn = get_connection()
    try:
        # Mark all previous tokens for this user as used before issuing a new one
        conn.execute(
            "UPDATE password_reset_tokens SET used = 1 WHERE user_id = ?",
            (row["id"],),
        )
        conn.execute(
            "INSERT INTO password_reset_tokens (user_id, token_hash, expires_at) "
            "VALUES (?, ?, ?)",
            (row["id"], token_hash, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    reset_link = f"{APP_BASE_URL}/?reset_token={plain_token}"
    _send_reset_email(body.email, reset_link)

    return _ok


# ============================================================
# POST /auth/reset-password
# ============================================================

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=32)

    @field_validator('new_password')
    @classmethod
    def password_complexity(cls, v: str) -> str:
        return _check_password_complexity(v)


@router.post("/reset-password", summary="Complete a password reset")
def reset_password(body: ResetPasswordRequest):
    token_hash = hash_reset_token(body.token)
    now = int(time.time())

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, user_id, expires_at, used FROM password_reset_tokens "
            "WHERE token_hash = ?",
            (token_hash,),
        ).fetchone()

        if not row or row["used"] or row["expires_at"] < now:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This reset link is invalid or has expired. Please request a new one.",
            )

        new_hash = hash_password(body.new_password)
        conn.execute(
            "UPDATE users SET password_hash = ?, updated_at = ? WHERE id = ?",
            (new_hash, now, row["user_id"]),
        )
        conn.execute(
            "UPDATE password_reset_tokens SET used = 1 WHERE id = ?",
            (row["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    return {"message": "Password updated successfully. You can now sign in."}


# ============================================================
# GET /auth/me
# ============================================================

@router.get("/me", summary="Return the current authenticated user")
def get_me(user: dict = Depends(get_current_user)):
    return user


# ============================================================
# PUT /auth/display-name
# ============================================================

# Allow letters (any script), digits, spaces, underscores, hyphens.
_DISPLAY_NAME_RE = re.compile(r'^[\w\s\-]+$', re.UNICODE)
_DISPLAY_NAME_MAX = 32


class UpdateDisplayNameRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=_DISPLAY_NAME_MAX)

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Display name must not be blank.')
        if len(v) > _DISPLAY_NAME_MAX:
            raise ValueError(f'Display name must not exceed {_DISPLAY_NAME_MAX} characters.')
        if not _DISPLAY_NAME_RE.match(v):
            raise ValueError(
                'Display name may only contain letters, numbers, spaces, underscores, or hyphens.'
            )
        return v


@router.put("/display-name", summary="Update the authenticated user's display name")
def update_display_name(
    body: UpdateDisplayNameRequest,
    user: dict = Depends(get_current_user),
):
    """
    Update the display name for the currently authenticated user.
    Validates: max 32 chars, letters/digits/spaces/underscores/hyphens only.
    """
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET display_name = ?, updated_at = strftime('%s','now') WHERE id = ?",
            (body.display_name, user["id"]),
        )
        conn.commit()
    finally:
        conn.close()

    return {"display_name": body.display_name}


# ============================================================
# Google OAuth2
# ============================================================

@router.get("/google/login", summary="Start Google OAuth2 flow")
def google_login():
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Google OAuth is not configured on this server.",
        )

    from urllib.parse import urlencode
    state = create_state_token()
    params = {
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "access_type": "online",
        "prompt": "select_account",
    }
    return RedirectResponse(
        url="https://accounts.google.com/o/oauth2/v2/auth?" + urlencode(params)
    )


@router.get("/google/callback", summary="Google OAuth2 callback")
async def google_callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    state: Optional[str] = None,
):
    if error or not code:
        return HTMLResponse(_oauth_error_page("Google sign-in was cancelled or failed"))

    if not state or not verify_state_token(state):
        return HTMLResponse(_oauth_error_page("Invalid OAuth state — please try again"))

    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

    if token_resp.status_code != 200:
        logger.error("[auth/google] token exchange failed: %s", token_resp.text)
        return HTMLResponse(_oauth_error_page("Failed to complete Google sign-in"))

    access_token = token_resp.json().get("access_token")
    if not access_token:
        return HTMLResponse(_oauth_error_page("No access token returned by Google"))

    # Fetch user info using the access token (avoids manual JWT decoding)
    async with httpx.AsyncClient() as client:
        info_resp = await client.get(
            "https://www.googleapis.com/oauth2/v3/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if info_resp.status_code != 200:
        return HTMLResponse(_oauth_error_page("Could not fetch your Google profile"))

    info = info_resp.json()
    email = info.get("email", "")
    name  = info.get("name") or email.split("@")[0]
    gid   = info.get("sub", "")

    if not email or not gid:
        return HTMLResponse(_oauth_error_page("Google did not return your email address"))

    user  = _get_or_create_oauth_user(email, name, "google", gid)
    token = create_access_token(user_id=user["id"], email=user["email"])
    return HTMLResponse(_oauth_success_page(token))



