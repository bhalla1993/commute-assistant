API Reference — DRT AI Transit Assistant
========================================

Base URL (local): http://localhost:8000

Authentication
- Most endpoints require a Bearer JWT in the `Authorization` header.
- Obtain tokens via the auth routes (see `api/auth_router.py`) or create test tokens in development.

Common headers
- `Authorization: Bearer <token>` — required for protected endpoints
- `X-Ad-Token: <token-id>` — used by `/chat` for ad-verified free queries (see monetization)

Endpoints
---------

POST /chat
- Description: Main chat endpoint. Sends user message to the local agent (and LLM fallback).
- Body (JSON):
  {
    "message": "What buses run near Oshawa GO Station?",
    "history": [],
    "latitude": 43.8975,
    "longitude": -78.8631
  }
- Response (200):
  {
    "reply": "Assistant text...",
    "history": [ /* updated conversation history objects */ ],
    "suggestions": ["Next bus", "Nearby stops"]
  }
- Notes: Free users are subject to daily quota and must include a valid `X-Ad-Token` header.

POST /chat/history
- Description: Save or update a chat session for the authenticated user.
- Body (JSON):
  {
    "messages": [{"role":"user","content":"..."}, ...],
    "session_id": 123  // optional for update
  }
- Response (201): {"session_id": 123}

GET /chat/history
- Description: Return the user's last 5 chat sessions (newest first).
- Response (200): {"sessions": [{"id": 1, "messages": [...], "created_at": "..."}, ...]}

GET /stops/nearby
- Query params: `lat` (required), `lon` (required), `radius` (optional, meters; default 500)
- Response: {"stops": [...], "count": N}

GET /delays/{stop_id}
- Path param: `stop_id` (string)
- Optional query: `date=YYYYMMDD` (defaults to today UTC)
- Response: {"stop_id": "...", "date": "YYYYMMDD", "trips": [ ... ]}

GET /alerts
- Query params: `route_id` (optional)
- Response: {"alerts": [...], "count": N, "available": true|false}

GET /vehicle/{trip_id}
- Path param: `trip_id` (string)
- Response: {"latitude": ..., "longitude": ..., "bearing": ..., "speed": ..., "trip_id": "..."}

GET /health
- Description: Service health check for poller + DB.
- Response: {"status": "ok"|"degraded", "poller": {...}, "db": {...}}

POST /subscription/checkout
- Description: Create a Stripe Checkout Session for Premium subscription.
- Auth: Required
- Response (200): {"checkout_url": "https://checkout.stripe.com/..."}
- Notes: Requires Stripe keys to be configured. See `docs/SUBSCRIPTIONS.md`.

POST /subscription/portal
- Description: Create a Stripe Customer Portal session to manage subscription.
- Auth: Required
- Response: {"portal_url": "..."}

POST /subscription/verify-payment
- Description: Fallback to verify user's subscription status by checking Stripe.
- Auth: Required
- Response: {"upgraded": true|false, "message": "..."}

POST /subscription/webhook
- Description: Stripe webhook receiver (not included in API docs). Configure `STRIPE_WEBHOOK_SECRET`.
- Notes: In local development set `ENV=local` to skip signature verification.

GET /config/flags
- Description: Returns current feature-flag status for frontend use.
- Response: {"subscriptions": true, "ads": true, ...}

Admin / debug endpoints
- `/config/admin/debug` — admin-only flags debug (requires auth)

Error responses
- 401 Unauthorized — missing/invalid JWT
- 403 Forbidden — ad verification failed or access denied
- 404 Not Found — resource not found (e.g., no trips for stop)
- 402 Payment Required — quota exceeded for free users
- 500 Server Error — unexpected server error

Notes for integrators
- Rate limiting: Many endpoints call an in-memory rate limiter (10 calls/min per user by default). Adjust in `api/endpoints.py` or `api/rate_limit.py`.
- Feature flags: See `docs/FEATURE_FLAGS.md` for how disabling features affects APIs (e.g., subscriptions off returns 503 for checkout).

