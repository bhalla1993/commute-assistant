# Feature Flags & Graceful Degradation Plan

## Overview
This document outlines feature flags for major use cases in the Commute Assistant app. Each flag allows disabling a feature without code changes, enabling graceful degradation if technical problems occur.

---

## 1. SUBSCRIPTIONS / PAYMENTS
**File**: `api/subscription_router.py`, `api/endpoints.py`

### Flag Configuration
```env
FEATURE_SUBSCRIPTIONS_ENABLED=true
```

### Behavior When Disabled
- Hide "Upgrade Now" button in UI
- All users treated as FREE tier
- `/subscription/checkout` returns 503 (Service Unavailable)
- `/subscription/status` returns free tier only
- Premium features not accessible

### Implementation Points
- **subscription_router.py** → `/checkout`, `/portal`, `/verify-payment` - return 503 if disabled
- **endpoints.py** → `/chat` - ignore premium tier, apply free rules to all
- **app.js** → Hide upgrade button/modal if flag false

### Graceful Message
```json
{
  "detail": "Subscription service temporarily unavailable. All users can access with free limits.",
  "status": "maintenance"
}
```

---

## 2. ADS / AD-GATING
**File**: `api/endpoints.py`, `api/ad_router.py` (if exists)

### Flag Configuration
```env
FEATURE_ADS_ENABLED=true
```

### Behavior When Disabled
- Free users get **unlimited queries** (no 3-query limit)
- No requirement for `X-Ad-Token` header
- `/ads/create-token` endpoint returns 503
- No ads shown to users
- Better UX but no ad revenue

### Implementation Points
- **endpoints.py** → `/chat` - skip ad token validation if disabled
- **quota.py** → `get_daily_query_count()` - return 0 (no limit) if disabled
- **app.js** → Don't show ad unit, don't require token

### Graceful Message
```json
{
  "message": "Ads temporarily unavailable. Enjoy unlimited queries!",
  "ads_enabled": false
}
```

---

## 3. REAL-TIME TRANSIT DATA (GTFS-RT)
**File**: `feeds/poller.py`, `engine/` endpoints

### Flag Configuration
```env
FEATURE_GTFS_RT_ENABLED=true
```

### Behavior When Disabled
- Use static GTFS schedule data only (no live updates)
- `/alerts`, `/delays`, `/vehicle-positions` return empty or stale data
- `/routes` still works with schedule data
- `/nearby` returns routes but no live status

### Implementation Points
- **feeds/poller.py** → Skip polling if disabled
- **engine/alerts.py** → Return empty alerts
- **engine/delays.py** → Return empty delay info
- **app.js** → Show "Live data unavailable, using schedule" message

### Graceful Message
```json
{
  "message": "Live transit data unavailable. Using static schedule.",
  "is_live": false,
  "timestamp": "2026-05-09T12:00:00Z"
}
```

---

## 4. AUTHENTICATION
**File**: `api/auth.py`

### Flag Configuration
```env
FEATURE_AUTH_ENABLED=true
```

### Behavior When Disabled
- Anonymous access allowed
- All users treated as `user_id="anonymous"`
- No login/signup required
- No JWT tokens needed
- Demo mode for testing

### Implementation Points
- **auth.py** → `get_current_user()` - return anonymous user if disabled
- **endpoints.py** → All endpoints work without auth
- **app.js** → Skip login screen, auto-login as anonymous

### Use Case
- Testing/demo mode
- Public transit info access

---

## 5. RATE LIMITING
**File**: `api/rate_limit.py`, `api/endpoints.py`

### Flag Configuration
```env
FEATURE_RATE_LIMITING_ENABLED=true
```

### Behavior When Disabled
- No rate limits applied
- Prevent DDoS protection removal but allow testing
- Remove per-user/per-IP checks

### Implementation Points
- **endpoints.py** → `/chat` - skip `_chat_rate_limiter.check()`
- **rate_limit.py** → All checks become no-ops

---

## 6. DATABASE PERSISTENCE
**File**: `db/database.py`

### Flag Configuration
```env
FEATURE_DATABASE_ENABLED=true
```

### Behavior When Disabled
- In-memory storage only (no SQLite)
- Data lost on restart
- Use for testing/demo

### Implementation Points
- **database.py** → Use in-memory dict instead of SQLite
- **quota.py** → Query in-memory store
- **subscription_router.py** → Query in-memory store

---

## 7. WEBHOOK PROCESSING (Stripe)
**File**: `api/subscription_router.py`

### Flag Configuration
```env
FEATURE_STRIPE_WEBHOOKS_ENABLED=true
```

### Behavior When Disabled
- Webhook endpoint still exists but doesn't process events
- Users must manually verify payment via `/verify-payment`
- Polling fallback becomes critical

### Implementation Points
- **subscription_router.py** → `/webhook` - return 200 but don't process if disabled
- **app.js** → Increase polling frequency if webhooks disabled
- Log: "Webhooks disabled, relying on polling"

---

## Configuration File Structure

### .env (Environment Variables)
```env
# Feature Flags (true/false)
FEATURE_SUBSCRIPTIONS_ENABLED=true
FEATURE_ADS_ENABLED=true
FEATURE_GTFS_RT_ENABLED=true
FEATURE_AUTH_ENABLED=true
FEATURE_RATE_LIMITING_ENABLED=true
FEATURE_DATABASE_ENABLED=true
FEATURE_STRIPE_WEBHOOKS_ENABLED=true

# Optional: Maintenance Mode (disables all non-essential features)
MAINTENANCE_MODE=false
```

### config.py (Centralized Flag Loading)
```python
import os
from typing import Dict

class FeatureFlags:
    """Centralized feature flag management"""
    
    SUBSCRIPTIONS_ENABLED = os.getenv("FEATURE_SUBSCRIPTIONS_ENABLED", "true").lower() == "true"
    ADS_ENABLED = os.getenv("FEATURE_ADS_ENABLED", "true").lower() == "true"
    GTFS_RT_ENABLED = os.getenv("FEATURE_GTFS_RT_ENABLED", "true").lower() == "true"
    AUTH_ENABLED = os.getenv("FEATURE_AUTH_ENABLED", "true").lower() == "true"
    RATE_LIMITING_ENABLED = os.getenv("FEATURE_RATE_LIMITING_ENABLED", "true").lower() == "true"
    DATABASE_ENABLED = os.getenv("FEATURE_DATABASE_ENABLED", "true").lower() == "true"
    STRIPE_WEBHOOKS_ENABLED = os.getenv("FEATURE_STRIPE_WEBHOOKS_ENABLED", "true").lower() == "true"
    
    # Maintenance mode overrides
    MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
    
    @classmethod
    def get_all(cls) -> Dict[str, bool]:
        """Return all flags as dict for frontend"""
        return {
            "subscriptions": cls.SUBSCRIPTIONS_ENABLED and not cls.MAINTENANCE_MODE,
            "ads": cls.ADS_ENABLED and not cls.MAINTENANCE_MODE,
            "gtfs_rt": cls.GTFS_RT_ENABLED and not cls.MAINTENANCE_MODE,
            "auth": cls.AUTH_ENABLED and not cls.MAINTENANCE_MODE,
            "rate_limiting": cls.RATE_LIMITING_ENABLED and not cls.MAINTENANCE_MODE,
            "database": cls.DATABASE_ENABLED and not cls.MAINTENANCE_MODE,
            "webhooks": cls.STRIPE_WEBHOOKS_ENABLED and not cls.MAINTENANCE_MODE,
            "maintenance": cls.MAINTENANCE_MODE,
        }
```

---

## Frontend Impact (app.js)

### New Endpoint: GET /config/flags
```javascript
async function loadFeatureFlags() {
  try {
    const res = await fetch('/config/flags');
    const flags = await res.json();
    
    window._featureFlags = flags;
    
    // Apply UI changes based on flags
    if (!flags.subscriptions) {
      document.getElementById('upgrade-modal')?.style.display = 'none';
      document.getElementById('btn-upgrade')?.style.display = 'none';
    }
    
    if (!flags.ads) {
      // Remove ad units
      document.getElementById('ad-unit')?.style.display = 'none';
    }
    
    if (!flags.maintenance) {
      showMaintenanceBanner("App under maintenance. Some features unavailable.");
    }
    
  } catch (e) {
    console.error('[flags] Failed to load feature flags:', e);
  }
}

// Call on app start
initApp().then(() => loadFeatureFlags());
```

---

## Scenario Testing Guide

### Scenario 1: Payment System Down
```bash
FEATURE_SUBSCRIPTIONS_ENABLED=false
# Result: Free tier only, no checkout option
```

### Scenario 2: Ad System Down
```bash
FEATURE_ADS_ENABLED=false
# Result: Unlimited free queries, no ads
```

### Scenario 3: Live Transit Data Down
```bash
FEATURE_GTFS_RT_ENABLED=false
# Result: Schedule-based queries only, no delays/alerts
```

### Scenario 4: Full Maintenance
```bash
MAINTENANCE_MODE=true
# Result: All non-essential features disabled
```

### Scenario 5: Demo/Testing Mode
```bash
FEATURE_AUTH_ENABLED=false
FEATURE_DATABASE_ENABLED=false
FEATURE_ADS_ENABLED=false
# Result: Anonymous access, in-memory storage, no ads
```

---

## Implementation Checklist

### Phase 1: Config Module
- [ ] Create `api/config.py` with FeatureFlags class
- [ ] Add all flags to .env
- [ ] Add `/config/flags` endpoint in api/main.py
- [ ] Validate flags on app startup

### Phase 2: Subscription Flag
- [ ] Check `SUBSCRIPTIONS_ENABLED` in `/checkout`
- [ ] Check flag in `/verify-payment`
- [ ] Check flag in `/status`
- [ ] Update `/chat` to ignore premium if disabled
- [ ] Update app.js to hide upgrade UI

### Phase 3: Ads Flag
- [ ] Check `ADS_ENABLED` in `/chat` endpoint
- [ ] Skip ad token validation if disabled
- [ ] Return unlimited quota if disabled
- [ ] Update quota.py

### Phase 4: GTFS-RT Flag
- [ ] Check `GTFS_RT_ENABLED` in feeds/poller.py
- [ ] Check flag in engine endpoints
- [ ] Return stale/empty data if disabled

### Phase 5: Frontend Integration
- [ ] Add `loadFeatureFlags()` call
- [ ] Conditionally render UI elements
- [ ] Show maintenance banner if needed
- [ ] Log flag status on page load

### Phase 6: Monitoring & Logging
- [ ] Log all flags at startup
- [ ] Add `/debug/flags` endpoint (admin only)
- [ ] Log when features disabled mid-operation

---

## Monitoring & Alerting

### Log on Startup
```
[startup] Feature Flags:
  ✅ SUBSCRIPTIONS_ENABLED=true
  ✅ ADS_ENABLED=true
  ✅ GTFS_RT_ENABLED=true
  ✅ AUTH_ENABLED=true
  ✅ RATE_LIMITING_ENABLED=true
  ✅ DATABASE_ENABLED=true
  ✅ STRIPE_WEBHOOKS_ENABLED=true
  MAINTENANCE_MODE=false
```

### Admin Debug Endpoint
```
GET /admin/flags
Response:
{
  "flags": {...},
  "warnings": [
    "GTFS_RT_ENABLED=false - Live data unavailable",
    "STRIPE_WEBHOOKS_ENABLED=false - Using polling fallback"
  ]
}
```

---

## Rollback Strategy

If a feature causes problems:

1. **Immediate**: Set flag to `false` in .env
2. **Restart**: `docker restart app` or manually restart
3. **Verify**: Check logs for graceful degradation messages
4. **Communicate**: User sees maintenance message
5. **Debug**: Fix root cause while feature disabled
6. **Re-enable**: Set flag to `true` and restart

---

## Priority & Dependencies

**Critical (must have):**
1. Subscriptions flag - Payment system
2. Ads flag - Revenue system
3. GTFS-RT flag - Core functionality

**Important (should have):**
4. Auth flag - For testing
5. Rate limiting flag - For load testing
6. Webhooks flag - Fallback mechanism

**Nice to have:**
7. Database flag - Demo mode

---

## Questions to Address

1. Should flags require app restart or hot-reload?
   - **Recommendation**: Restart required for safety, but log changes

2. Should frontend cache flags or fetch on every session?
   - **Recommendation**: Fetch once on app load, cache in sessionStorage

3. Should disabled features return 503 or just be unavailable?
   - **Recommendation**: 503 for critical paths, graceful degradation for others

4. Should there be a flag for each Stripe object (Customer, Subscription, etc.)?
   - **Recommendation**: One `SUBSCRIPTIONS_ENABLED` flag covers all

---

## Next Steps

1. **Create `api/config.py`** with FeatureFlags class
2. **Add `/config/flags` endpoint** for frontend
3. **Implement Phase 1-3** (most impactful)
4. **Add logging** at startup
5. **Document in README** how to use flags
6. **Test each scenario** in staging before production

---

**Version**: 1.0  
**Last Updated**: 2026-05-09  
**Status**: Plan Ready for Implementation
