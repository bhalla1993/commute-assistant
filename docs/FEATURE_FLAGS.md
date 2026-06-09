Feature Flags — Runtime configuration
====================================

Purpose
- Feature flags allow turning features on/off at runtime via environment variables.
- Use them to gracefully degrade if a provider or integration is broken.

Where flags are loaded
- Flags are defined and read from `transit-backend/api/config.py` (class `FeatureFlags`).
- The frontend can GET `/config/flags` to adapt UI behavior.

Flags (env names)
- `FEATURE_SUBSCRIPTIONS_ENABLED` — true/false (controls Stripe checkout, portal, verify-payment)
- `FEATURE_ADS_ENABLED` — true/false (controls ad gating and free quota enforcement)
- `FEATURE_GTFS_RT_ENABLED` — true/false (enable/disable live GTFS-RT polling and live data)
- `FEATURE_AUTH_ENABLED` — true/false (enable/disable auth; when false, anonymous/demo mode)
- `FEATURE_RATE_LIMITING_ENABLED` — true/false (enable/disable rate limits)
- `FEATURE_DATABASE_ENABLED` — true/false (use SQLite persistence vs in-memory)
- `FEATURE_STRIPE_WEBHOOKS_ENABLED` — true/false (process webhooks or no-op)
- `MAINTENANCE_MODE` — true/false (global kill-switch; disables non-essential features)

Behavioral notes
- `FEATURE_SUBSCRIPTIONS_ENABLED=false`
  - `/subscription/checkout` and `/subscription/portal` should return 503 (Service Unavailable).
  - `/subscription/status` should report `free` for all users.
  - The frontend should hide upgrade UI when `/config/flags` indicates subscriptions disabled.

- `FEATURE_ADS_ENABLED=false`
  - Free users are not required to supply `X-Ad-Token` and receive unlimited queries.
  - The quota system can be adjusted to treat all users as unlimited when ads are disabled.

- `FEATURE_GTFS_RT_ENABLED=false`
  - The poller should not run; `/delays`, `/alerts`, `/vehicle` should return schedule-only or empty data.

- `FEATURE_STRIPE_WEBHOOKS_ENABLED=false`
  - Webhook endpoint should accept events but not change DB state. Use `/subscription/verify-payment` as manual fallback.

Code locations to update when adding flag checks
- `transit-backend/api/subscription_router.py` — check `FeatureFlags.SUBSCRIPTIONS_ENABLED` in `/checkout`, `/portal`, `/verify-payment`, and `/webhook`.
- `transit-backend/api/endpoints.py` — check `FeatureFlags.ADS_ENABLED` before enforcing ad token and quota.
- `transit-backend/feeds/poller.py` — check `FeatureFlags.GTFS_RT_ENABLED` before starting polling.
- `transit-backend/api/auth.py` — honor `FeatureFlags.AUTH_ENABLED` to return anonymous user when false.
- `transit-backend/api/rate_limit.py` — return no-op when `FeatureFlags.RATE_LIMITING_ENABLED` is false.

How to enable/disable (example `.env`)
```
FEATURE_SUBSCRIPTIONS_ENABLED=true
FEATURE_ADS_ENABLED=true
FEATURE_GTFS_RT_ENABLED=true
FEATURE_AUTH_ENABLED=true
FEATURE_RATE_LIMITING_ENABLED=true
FEATURE_DATABASE_ENABLED=true
FEATURE_STRIPE_WEBHOOKS_ENABLED=true
MAINTENANCE_MODE=false
```

Admin/debug endpoints
- `/config/flags` — public endpoint returns flags to frontend
- `/config/admin/debug` — admin-only endpoint (requires auth) returns flags, warnings, and validation results

Testing flags
- Update `.env` and restart the server to apply changes.
- Confirm effect with `curl http://localhost:8000/config/flags` and the affected endpoints.

