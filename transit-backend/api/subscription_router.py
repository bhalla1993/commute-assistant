"""
Subscription endpoints backed by Stripe.

Routes:
  GET  /subscription/status    — tier, daily quota usage, renewal date
  POST /subscription/checkout  — create Stripe Checkout Session → return URL
  POST /subscription/portal    — create Stripe Customer Portal Session → return URL
  POST /subscription/webhook   — Stripe webhook (subscription lifecycle events)

Environment variables required (in .env):
  STRIPE_SECRET_KEY        — sk_live_… or sk_test_…
  STRIPE_WEBHOOK_SECRET    — whsec_…  (from Stripe Dashboard → Webhooks)
  STRIPE_PREMIUM_PRICE_ID  — price_… (your $2.99/mo recurring price object)
  APP_BASE_URL             — https://your-domain.com  (for redirect URLs)
"""
import json
import logging
import os

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import get_current_user
from api.quota import FREE_DAILY_LIMIT, get_daily_query_count, get_user_tier
from db.database import get_connection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/subscription", tags=["subscription"])

stripe.api_key          = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET   = os.getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PREMIUM_PRICE_ID = os.getenv("STRIPE_PREMIUM_PRICE_ID", "")
APP_BASE_URL            = os.getenv("APP_BASE_URL", "http://localhost:8000")


# ── GET /subscription/status ──────────────────────────────────────────────

@router.get("/status", summary="Get subscription tier and daily quota usage")
def get_status(user: dict = Depends(get_current_user)):
    user_id = user["id"]
    tier    = get_user_tier(user_id)
    
    # 🔄 BI-DIRECTIONAL AUTO-SYNC WITH STRIPE
    
    if tier == "free":
        # Direction 1: If DB shows "free" but Stripe has active subscription, upgrade user
        has_active, active_sub = _has_active_subscription(user_id)
        if has_active:
            logger.info(f"[status] Auto-sync UP: User {user_id} has active Stripe subscription but DB shows free. Upgrading...")
            _set_premium(user_id, active_sub["id"])
            tier = "premium"
    else:
        # Direction 2: If DB shows "premium" but Stripe subscription is cancelled/deleted, downgrade user
        # First, get the stored subscription ID from database
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT stripe_subscription_id FROM users WHERE id = ?", (user_id,)
            ).fetchone()
            stored_sub_id = row["stripe_subscription_id"] if row else None
        finally:
            conn.close()
        
        if stored_sub_id:
            # Verify this subscription is still active in Stripe
            is_still_valid = _verify_subscription_is_valid(stored_sub_id)
            if not is_still_valid:
                logger.warning(f"[status] Auto-sync DOWN: User {user_id} marked premium but Stripe subscription {stored_sub_id} is no longer valid. Downgrading...")
                _revoke_premium(user_id)
                tier = "free"
    
    queries_used      = get_daily_query_count(user_id)
    queries_remaining = max(0, FREE_DAILY_LIMIT - queries_used) if tier == "free" else None

    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT subscription_expires_at FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        renewal_date = row["subscription_expires_at"] if row else None
    finally:
        conn.close()

    return {
        "tier":               tier,
        "queries_used_today": queries_used,
        "queries_remaining":  queries_remaining,
        "daily_limit":        FREE_DAILY_LIMIT if tier == "free" else None,
        "renewal_date":       renewal_date,
    }


# ── POST /subscription/checkout ───────────────────────────────────────────

@router.post("/checkout", summary="Start a Stripe Checkout session for Premium")
def create_checkout(user: dict = Depends(get_current_user)):
    try:
        logger.info(f"[checkout] START - User {user.get('id')}")
        
        if not stripe.api_key or not STRIPE_PREMIUM_PRICE_ID:
            logger.error("[checkout] Payment service not configured")
            raise HTTPException(status_code=503, detail="Payment service is not configured.")

        user_id = user["id"]
        email   = user.get("email", "")
        logger.info(f"[checkout] User ID: {user_id}, Email: {email}")

        # Get or create a Stripe Customer
        logger.info(f"[checkout] Getting Stripe customer ID...")
        customer_id = _get_stripe_customer_id(user_id)
        logger.info(f"[checkout] Customer ID from DB: {customer_id}")
        
        if not customer_id:
            logger.info(f"[checkout] No customer ID in DB, creating new Stripe customer...")
            try:
                customer = stripe.Customer.create(email=email, metadata={"user_id": user_id})
                customer_id = customer.id
                logger.info(f"[checkout] Created customer: {customer_id}")
                _save_stripe_customer_id(user_id, customer_id)
                logger.info(f"[checkout] Saved customer ID to DB")
            except stripe.StripeError as exc:
                logger.error(f"[checkout] Failed to create customer: {exc}")
                raise HTTPException(status_code=502, detail="Could not initiate checkout. Please try again.")

        # Try to create checkout session
        logger.info(f"[checkout] Creating checkout session with customer {customer_id}...")
        try:
            session = stripe.checkout.Session.create(
                customer=customer_id,
                payment_method_types=["card"],
                line_items=[{"price": STRIPE_PREMIUM_PRICE_ID, "quantity": 1}],
                mode="subscription",
                success_url=f"{APP_BASE_URL}/?checkout=success",
                cancel_url=f"{APP_BASE_URL}/?checkout=cancel",
                metadata={"user_id": user_id},
            )
            logger.info(f"[checkout] Session created successfully: {session.id}")
            return {"checkout_url": session.url}
            
        except stripe.error.InvalidRequestError as exc:
            # Check if the error is "No such customer"
            error_msg = str(exc)
            if "No such customer" in error_msg:
                logger.warning(f"[checkout] Stored customer {customer_id} doesn't exist in Stripe. Deleting from DB and creating new customer...")
                
                # Clear the bad customer ID from database
                conn = get_connection()
                try:
                    conn.execute("UPDATE users SET stripe_customer_id = NULL WHERE id = ?", (user_id,))
                    conn.commit()
                    logger.info(f"[checkout] Cleared bad customer ID from database")
                finally:
                    conn.close()
                
                # Create a new customer
                try:
                    logger.info(f"[checkout] Creating new Stripe customer to replace deleted one...")
                    customer = stripe.Customer.create(email=email, metadata={"user_id": user_id})
                    customer_id = customer.id
                    logger.info(f"[checkout] Created new customer: {customer_id}")
                    _save_stripe_customer_id(user_id, customer_id)
                    logger.info(f"[checkout] Saved new customer ID to DB")
                    
                    # Retry checkout session with new customer
                    logger.info(f"[checkout] Retrying checkout session with new customer {customer_id}...")
                    session = stripe.checkout.Session.create(
                        customer=customer_id,
                        payment_method_types=["card"],
                        line_items=[{"price": STRIPE_PREMIUM_PRICE_ID, "quantity": 1}],
                        mode="subscription",
                        success_url=f"{APP_BASE_URL}/?checkout=success",
                        cancel_url=f"{APP_BASE_URL}/?checkout=cancel",
                        metadata={"user_id": user_id},
                    )
                    logger.info(f"[checkout] Retry successful! Session created: {session.id}")
                    return {"checkout_url": session.url}
                    
                except stripe.StripeError as e:
                    logger.error(f"[checkout] Failed to create new customer or retry checkout: {e}")
                    raise HTTPException(status_code=502, detail="Could not initiate checkout. Please try again.")
            else:
                # Some other invalid request error
                logger.error(f"[checkout] Stripe invalid request error: {exc}")
                raise HTTPException(status_code=502, detail="Could not initiate checkout. Please try again.")
                
        except stripe.StripeError as exc:
            logger.error(f"[checkout] Stripe error: {exc}")
            raise HTTPException(status_code=502, detail="Could not initiate checkout. Please try again.")
    
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"[checkout] UNEXPECTED ERROR: {type(exc).__name__}: {exc}", exc_info=True)
        raise HTTPException(status_code=502, detail=f"Checkout failed: {str(exc)}")


# ── POST /subscription/portal ─────────────────────────────────────────────

@router.post("/portal", summary="Open Stripe Customer Portal (manage/cancel subscription)")
def create_portal(user: dict = Depends(get_current_user)):
    if not stripe.api_key:
        raise HTTPException(status_code=503, detail="Payment service is not configured.")

    customer_id = _get_stripe_customer_id(user["id"])
    if not customer_id:
        raise HTTPException(status_code=404, detail="No active subscription found.")

    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f"{APP_BASE_URL}/",
        )
    except stripe.StripeError as exc:
        logger.error(f"Stripe portal session creation failed: {exc}")
        raise HTTPException(status_code=502, detail="Could not open billing portal. Please try again.")

    return {"portal_url": session.url}


# ── POST /subscription/verify-payment ────────────────────────────────────

@router.post("/verify-payment", summary="Verify and upgrade user after successful checkout (fallback for webhook)")
def verify_payment(user: dict = Depends(get_current_user)):
    """
    This endpoint checks Stripe to see if the user has an active subscription.
    Used as a fallback when webhooks aren't configured (e.g., during local testing).
    """
    if not stripe.api_key:
        logger.error("[subscription] Stripe API key not configured")
        raise HTTPException(status_code=503, detail="Payment service is not configured.")

    user_id = user["id"]
    logger.info(f"[subscription] Verifying payment for user {user_id}")
    
    # Get the user's Stripe customer ID
    customer_id = _get_stripe_customer_id(user_id)
    logger.info(f"[subscription] Customer ID for user {user_id}: {customer_id}")
    
    if not customer_id:
        logger.warning(f"[subscription] No Stripe customer found for user {user_id}")
        return {"upgraded": False, "message": "No Stripe customer found"}
    
    try:
        # Get all subscriptions for this customer
        subscriptions = stripe.Subscription.list(customer=customer_id, limit=10, status='all')
        logger.info(f"[subscription] Found {len(subscriptions.data)} subscriptions for customer {customer_id}")
        
        # Look for the most recent active subscription
        active_sub = None
        for sub in subscriptions.data:
            logger.info(f"[subscription] Subscription {sub.id}: status={sub.status}, created={sub.created}")
            if sub.status in ("active", "trialing"):
                active_sub = sub
                break
        
        if active_sub:
            subscription_id = active_sub.id
            logger.info(f"[subscription] Found active subscription {subscription_id} for user {user_id}")
            # Upgrade user to premium
            _set_premium(user_id, subscription_id)
            logger.info(f"[subscription] User {user_id} upgraded to premium via verify-payment")
            return {
                "upgraded": True, 
                "message": "User upgraded to premium", 
                "subscription_id": subscription_id,
                "status": active_sub.status
            }
        else:
            # Log all subscription statuses for debugging
            statuses = [f"{s.id}:{s.status}" for s in subscriptions.data]
            logger.warning(f"[subscription] No active subscription found for customer {customer_id}. Statuses: {statuses}")
            return {"upgraded": False, "message": "No active subscription found", "all_subscriptions": statuses}
            
    except stripe.StripeError as exc:
        logger.error(f"[subscription] Failed to verify payment for user {user_id}: {exc}")
        raise HTTPException(status_code=502, detail=f"Could not verify payment: {str(exc)}")


# ── GET /subscription/debug ────────────────────────────────────────────────

@router.get("/debug", summary="Debug: Check current subscription status in DB and Stripe")
def debug_subscription(user: dict = Depends(get_current_user)):
    """
    Debug endpoint to check what's in the database and Stripe.
    Shows if there's a mismatch between DB and Stripe.
    """
    user_id = user["id"]
    
    # Check database
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id, email, subscription_tier, stripe_customer_id, stripe_subscription_id FROM users WHERE id = ?",
            (user_id,)
        ).fetchone()
    finally:
        conn.close()
    
    db_info = {
        "user_id": row["id"],
        "email": row["email"],
        "db_tier": row["subscription_tier"],
        "stripe_customer_id": row["stripe_customer_id"],
        "stripe_subscription_id": row["stripe_subscription_id"]
    } if row else {}
    
    # Check Stripe
    stripe_info = {}
    customer_id = db_info.get("stripe_customer_id")
    
    if customer_id and stripe.api_key:
        try:
            subscriptions = stripe.Subscription.list(customer=customer_id, limit=10, status='all')
            stripe_info["stripe_subscriptions"] = [
                {
                    "id": sub.id,
                    "status": sub.status,
                    "created": sub.created,
                    "current_period_start": sub.current_period_start,
                    "current_period_end": sub.current_period_end
                }
                for sub in subscriptions.data
            ]
        except stripe.StripeError as exc:
            stripe_info["error"] = str(exc)
    
    return {
        "database": db_info,
        "stripe": stripe_info,
        "mismatch": db_info.get("db_tier") == "free" and len(stripe_info.get("stripe_subscriptions", [])) > 0
    }


# ── POST /subscription/webhook ────────────────────────────────────────────

@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    """Handles Stripe webhook events for the full subscription lifecycle."""
    # For local testing without bank verification, set ENV=local to skip signature check
    skip_signature = os.getenv("ENV") == "local"
    
    if not STRIPE_WEBHOOK_SECRET and not skip_signature:
        logger.warning("[stripe] STRIPE_WEBHOOK_SECRET not set — webhook rejected.")
        raise HTTPException(status_code=503, detail="Webhook not configured.")

    payload    = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        if skip_signature:
            # Local testing mode: parse without signature verification
            event = json.loads(payload.decode('utf-8'))
            logger.warning("[stripe] WEBHOOK SIGNATURE VERIFICATION SKIPPED (local testing mode)")
        else:
            # Production: verify signature
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except stripe.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid webhook signature.")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload.")

    etype = event["type"]
    logger.info(f"[stripe webhook] received: {etype}")

    if etype == "checkout.session.completed":
        obj             = event["data"]["object"]
        user_id         = obj.get("metadata", {}).get("user_id")
        subscription_id = obj.get("subscription")
        if user_id and subscription_id:
            _set_premium(user_id, subscription_id)

    elif etype == "invoice.paid":
        sub_id = event["data"]["object"].get("subscription")
        if sub_id:
            try:
                subscription = stripe.Subscription.retrieve(sub_id)
                user_id      = subscription.get("metadata", {}).get("user_id")
                if not user_id:
                    user_id = _user_id_by_stripe_sub(sub_id)
                if user_id:
                    _renew_premium(user_id, subscription.get("current_period_end"))
            except stripe.StripeError as exc:
                logger.error(f"[stripe] Failed to retrieve subscription {sub_id}: {exc}")

    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        obj    = event["data"]["object"]
        sub_id = obj.get("id")
        user_id = obj.get("metadata", {}).get("user_id") or _user_id_by_stripe_sub(sub_id)
        if user_id:
            _revoke_premium(user_id)

    return {"received": True}


# ── Internal DB helpers ───────────────────────────────────────────────────

def _get_stripe_customer_id(user_id: str) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT stripe_customer_id FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return row["stripe_customer_id"] if row else None
    finally:
        conn.close()


def _has_active_subscription(user_id: str) -> tuple[bool, dict | None]:
    """
    Check if user has an active subscription in Stripe.
    Returns: (has_active, subscription_dict)
    """
    customer_id = _get_stripe_customer_id(user_id)
    if not customer_id:
        return False, None
    
    try:
        subscriptions = stripe.Subscription.list(customer=customer_id, limit=10, status='all')
        for sub in subscriptions.data:
            if sub.status in ("active", "trialing"):
                return True, {
                    "id": sub.id,
                    "status": sub.status,
                    "period_end": sub.current_period_end,
                    "price_id": sub.items.data[0].price.id if sub.items.data else None
                }
        return False, None
    except stripe.StripeError as exc:
        logger.error(f"[subscription] Error checking active subscriptions for user {user_id}: {exc}")
        return False, None


def _verify_subscription_is_valid(subscription_id: str) -> bool:
    """
    Verify that a stored subscription ID is still active in Stripe.
    Returns True if subscription is active/trialing, False if cancelled/expired/not found.
    """
    if not subscription_id:
        return False
    
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        is_active = sub.status in ("active", "trialing")
        logger.debug(f"[subscription] Subscription {subscription_id}: status={sub.status}, active={is_active}")
        return is_active
    except stripe.error.InvalidRequestError:
        # Subscription doesn't exist or was deleted
        logger.warning(f"[subscription] Subscription {subscription_id} not found in Stripe (deleted?)")
        return False
    except stripe.StripeError as exc:
        # Network error or other Stripe issue - don't downgrade, just warn
        logger.warning(f"[subscription] Could not verify subscription {subscription_id}: {exc}")
        return True  # Assume valid if we can't reach Stripe


def _save_stripe_customer_id(user_id: str, customer_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET stripe_customer_id = ? WHERE id = ?", (customer_id, user_id)
        )
        conn.commit()
    finally:
        conn.close()


def _set_premium(user_id: str, subscription_id: str) -> None:
    """Upgrade user to premium and store Stripe subscription details."""
    period_end = None
    
    # Fetch subscription details from Stripe to get period_end date
    try:
        sub = stripe.Subscription.retrieve(subscription_id)
        period_end = sub.current_period_end
        logger.info(f"[subscription] Retrieved subscription {subscription_id}: period_end={period_end}")
    except stripe.StripeError as exc:
        logger.warning(f"[subscription] Could not fetch subscription details: {exc}")
    
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE users 
               SET subscription_tier = 'premium', 
                   stripe_subscription_id = ?,
                   subscription_expires_at = ?
               WHERE id = ?""",
            (subscription_id, period_end, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[subscription] User {user_id} upgraded to premium (sub={subscription_id}, expires={period_end})")


def _renew_premium(user_id: str, period_end: int | None) -> None:
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE users SET subscription_tier = 'premium', subscription_expires_at = ? WHERE id = ?",
            (period_end, user_id),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[subscription] User {user_id} premium renewed until {period_end}")


def _revoke_premium(user_id: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE users
               SET subscription_tier = 'free',
                   stripe_subscription_id = NULL,
                   subscription_expires_at = NULL
               WHERE id = ?""",
            (user_id,),
        )
        conn.commit()
    finally:
        conn.close()
    logger.info(f"[subscription] User {user_id} downgraded to free")


def _user_id_by_stripe_sub(subscription_id: str) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT id FROM users WHERE stripe_subscription_id = ?", (subscription_id,)
        ).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()
