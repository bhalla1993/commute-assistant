Subscriptions & Stripe Integration
=================================

Overview
- The app supports an optional premium subscription (monthly) via Stripe.
- Key endpoints are in `transit-backend/api/subscription_router.py`:
  - `GET /subscription/status`
  - `POST /subscription/checkout`
  - `POST /subscription/portal`
  - `POST /subscription/verify-payment`
  - `POST /subscription/webhook` (Stripe webhook receiver)

Environment variables
- `STRIPE_SECRET_KEY` — your Stripe secret key (sk_test_... or sk_live_...)
- `STRIPE_WEBHOOK_SECRET` — webhook signing secret (whsec_...)
- `STRIPE_PREMIUM_PRICE_ID` — price_... for the recurring subscription
- `APP_BASE_URL` — public URL used for success/cancel/return URLs

Local development notes
- For local testing, webhooks are hard to configure. The app supports two ways to handle this:
  1. Use a tunnel (ngrok, cloudflared) and register a webhook URL with Stripe.
  2. Use `ENV=local` in `.env` to skip signature verification for the webhook endpoint (only for local dev).

Checkout flow
- `/subscription/checkout` will create (or reuse) a Stripe Customer, then create a Checkout Session in `subscription` mode.
- The endpoint returns `checkout_url` which the frontend should open.
- On successful payment Stripe will emit `checkout.session.completed` and `invoice.paid` events; the webhook handler upgrades or renews user subscriptions.

Webhook handling
- By default, the webhook verifies Stripe signatures using `STRIPE_WEBHOOK_SECRET`.
- `ENV=local` disables signature verification for faster local iteration.
- Webhook events processed:
  - `checkout.session.completed` — sets premium for user using metadata.user_id
  - `invoice.paid` — renews premium (updates `subscription_expires_at`)
  - `customer.subscription.deleted` / `customer.subscription.paused` — revoke premium

Manual verification endpoint
- If webhooks are not available, `POST /subscription/verify-payment` can be called by an authenticated user to let the server check Stripe directly and upgrade the user if an active subscription exists.

Testing tips
- Use Stripe test keys and the Stripe Dashboard to simulate events.
- When testing checkout in dev, ensure `APP_BASE_URL` points to where the browser can be redirected (ngrok URL or local frontend).

Security
- Never commit Stripe keys to source control. Use environment variables or secrets management.
- Enforce `FEATURE_SUBSCRIPTIONS_ENABLED` flag to disable payment flows during maintenance.

