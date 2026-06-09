"""
Ad token endpoints — gate free-tier queries behind ad views.

Flow:
  1. Frontend calls POST /ads/token   → server validates quota, creates a token
  2. Frontend shows the ad for >= MIN_AD_SECONDS while simultaneously
     starting the /chat request (parallel, result held until ad done)
  3. Frontend calls POST /ads/complete → server validates minimum watch time,
     marks token used
  4. Frontend sends the /chat request with X-Ad-Token header (or awaits it
     if it resolved already)

The X-Ad-Token header on /chat is cross-checked against the used ad_tokens
table to prevent bypassing the ad flow via direct API calls.
"""
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.auth import get_current_user
from api.quota import FREE_DAILY_LIMIT, MIN_AD_SECONDS, get_daily_query_count, get_user_tier
from db.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ads", tags=["ads"])

AD_TOKEN_TTL = 300  # 5-minute window to complete the ad flow


class AdCompleteRequest(BaseModel):
    token_id: str


@router.post("/token", summary="Create a single-use ad token (free users only)")
def create_ad_token(user: dict = Depends(get_current_user)):
    """
    Called by the frontend before showing an ad.
    Validates daily quota and returns a token the frontend must pass back
    after the ad countdown completes, and again in the X-Ad-Token header
    on /chat.
    """
    user_id = user["id"]
    tier = get_user_tier(user_id)

    if tier == "premium":
        raise HTTPException(
            status_code=400,
            detail={"reason": "not_required", "message": "Premium users do not need ad tokens."},
        )

    count = get_daily_query_count(user_id)
    if count >= FREE_DAILY_LIMIT:
        raise HTTPException(
            status_code=402,
            detail={
                "reason": "quota_exceeded",
                "message": (
                    f"You've used your {FREE_DAILY_LIMIT} free "
                    "queries for today. Upgrade to Premium for unlimited access."
                ),
            },
        )

    token_id   = str(uuid.uuid4())
    now        = int(time.time())
    expires_at = now + AD_TOKEN_TTL

    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO ad_tokens (id, user_id, created_at, expires_at, used) VALUES (?, ?, ?, ?, 0)",
            (token_id, user_id, now, expires_at),
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "token_id":       token_id,
        "expires_at":     expires_at,
        "min_ad_seconds": MIN_AD_SECONDS,
    }


@router.post("/complete", summary="Validate ad was watched; mark token as used")
def complete_ad(body: AdCompleteRequest, user: dict = Depends(get_current_user)):
    """
    Called by the frontend after the ad countdown finishes.
    Validates ownership, TTL, minimum watch time, and marks the token used.
    The same token_id must then be sent as X-Ad-Token on the /chat request.
    """
    user_id = user["id"]
    now     = int(time.time())

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, user_id, created_at, expires_at, used FROM ad_tokens WHERE id = ?",
            (body.token_id,),
        ).fetchone()

        if not row:
            raise HTTPException(
                status_code=404,
                detail={"reason": "invalid_token", "message": "Token not found."},
            )
        if row["user_id"] != user_id:
            raise HTTPException(
                status_code=403,
                detail={"reason": "invalid_token", "message": "Token does not belong to this user."},
            )
        if row["used"]:
            raise HTTPException(
                status_code=409,
                detail={"reason": "already_used", "message": "This token has already been used."},
            )
        if now > row["expires_at"]:
            raise HTTPException(
                status_code=410,
                detail={"reason": "token_expired", "message": "Token expired. Please start a new query."},
            )
        elapsed = now - row["created_at"]
        if elapsed < MIN_AD_SECONDS:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason": "ad_too_short",
                    "message": f"Ad must be shown for at least {MIN_AD_SECONDS} seconds.",
                },
            )

        conn.execute("UPDATE ad_tokens SET used = 1 WHERE id = ?", (body.token_id,))
        conn.commit()
    finally:
        conn.close()

    return {"verified": True}
