# Feature Flags - Implementation Roadmap

## ✅ COMPLETED

### 1. Core Infrastructure
- ✅ Created `api/config.py` with FeatureFlags class
- ✅ Created `api/config_router.py` with two endpoints:
  - `GET /config/flags` - Frontend flag check
  - `GET /config/admin/debug` - Admin debug info
- ✅ Integrated into `api/main.py`:
  - Added config_router registration
  - Added FeatureFlags.log_startup() call
  - Validates config on startup

### 2. Available Flags (Test Now)
```bash
# Test the new endpoints
curl http://localhost:8000/config/flags
curl http://localhost:8000/config/admin/debug -H "Authorization: Bearer <token>"
```

---

## 📋 NEXT STEPS - Implementation Phase 2-7

### Phase 2: Subscription Flag Implementation
**File**: `api/subscription_router.py`

**Changes Needed**:
```python
from api.config import FeatureFlags

@router.post("/checkout")
def create_checkout(user: dict = Depends(get_current_user)):
    # ADD THIS AT START:
    if not FeatureFlags.SUBSCRIPTIONS_ENABLED:
        logger.warning("[checkout] Subscriptions disabled - returning 503")
        raise HTTPException(
            status_code=503, 
            detail="Subscription service temporarily unavailable. All users can access with free limits."
        )
    
    # Rest of existing code...
```

**Also Update**:
- `/verify-payment` endpoint - Add same check
- `/portal` endpoint - Add same check
- `/status` endpoint - Return free tier if subscriptions disabled

---

### Phase 3: Ads Flag Implementation
**File**: `api/endpoints.py` (in `/chat` endpoint)

**Changes Needed**:
```python
from api.config import FeatureFlags

@router.post("/chat")
def chat(user: dict = Depends(get_current_user), request: Request = None):
    # ... existing code ...
    
    if user and 'id' in user:
        tier = get_user_tier(user['id'])
        
        # ADD THIS:
        if tier == 'free' and FeatureFlags.ADS_ENABLED:
            # EXISTING: Enforce 3-query daily limit
            # EXISTING: Require ad token
        elif tier == 'free' and not FeatureFlags.ADS_ENABLED:
            # NEW: Skip ad requirement, give unlimited queries
            logger.info("[chat] Ads disabled - allowing unlimited free queries")
            # Skip the ad token check
        
        # ... rest of code ...
```

**Also Update**: `api/quota.py`
```python
def get_daily_query_count(user_id: str) -> int:
    """Get queries used today. Returns 0 if ads disabled."""
    from api.config import FeatureFlags
    
    if not FeatureFlags.ADS_ENABLED:
        return 0  # No limit
    
    # existing code...
```

---

### Phase 4: GTFS-RT Flag Implementation
**File**: `feeds/poller.py`

**Changes Needed**:
```python
from api.config import FeatureFlags

def start_poller():
    """Start GTFS-RT poller if enabled."""
    if not FeatureFlags.GTFS_RT_ENABLED:
        logger.warning("[poller] GTFS-RT disabled - poller will not start")
        return
    
    # existing code...
```

**Also Update**: `engine/alerts.py`, `engine/delays.py`
```python
def get_active_alerts():
    """Get alerts if GTFS-RT enabled."""
    from api.config import FeatureFlags
    
    if not FeatureFlags.GTFS_RT_ENABLED:
        logger.debug("[alerts] GTFS-RT disabled - returning empty")
        return []
    
    # existing code...
```

---

### Phase 5: Auth Flag Implementation
**File**: `api/auth.py`

**Changes Needed**:
```python
def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer)) -> dict:
    """
    Return authenticated user, or anonymous user if auth disabled.
    """
    from api.config import FeatureFlags
    
    # If auth disabled, allow anonymous access
    if not FeatureFlags.AUTH_ENABLED:
        logger.debug("[auth] AUTH disabled - returning anonymous user")
        return {
            "id": "anonymous",
            "email": "anonymous@example.com",
            "display_name": "Anonymous"
        }
    
    # existing auth logic...
```

---

### Phase 6: Rate Limiting Flag Implementation
**File**: `api/endpoints.py` (in `/chat` endpoint)

**Changes Needed**:
```python
@router.post("/chat")
def chat(...):
    # Check rate limiting if enabled
    if FeatureFlags.RATE_LIMITING_ENABLED:
        key = f"user:{user['id']}" if user and 'id' in user else f"ip:{request.client.host if request else 'unknown'}"
        _chat_rate_limiter.check(key)
    else:
        logger.debug("[chat] Rate limiting disabled")
    
    # rest of code...
```

---

### Phase 7: Frontend Integration
**File**: `frontend/app.js`

**Changes Needed**:
```javascript
// Add this function after initApp()
async function loadFeatureFlags() {
  try {
    const res = await fetch('/config/flags');
    if (!res.ok) {
      console.warn('[flags] Failed to load flags:', res.status);
      return;
    }
    
    const flags = await res.json();
    window._featureFlags = flags;
    
    console.log('[flags] Loaded flags:', flags);
    
    // Hide/show UI based on flags
    if (!flags.subscriptions) {
      const modal = document.getElementById('upgrade-modal');
      const btn = document.getElementById('btn-upgrade');
      if (modal) modal.style.display = 'none';
      if (btn) btn.style.display = 'none';
      console.log('[flags] Subscriptions disabled - hiding upgrade UI');
    }
    
    if (!flags.ads) {
      const adUnit = document.getElementById('ad-unit');
      if (adUnit) adUnit.style.display = 'none';
      console.log('[flags] Ads disabled - hiding ad unit');
    }
    
    if (flags.maintenance) {
      showMaintenanceBanner("🚨 App under maintenance. Some features unavailable.");
    }
    
  } catch (e) {
    console.error('[flags] Error loading feature flags:', e);
  }
}

// Call after auth loads
initApp().then(() => {
  console.log('[app] Calling loadFeatureFlags...');
  return loadFeatureFlags();
});
```

---

## Testing Each Scenario

### Test 1: Disable Subscriptions
```bash
# In .env
FEATURE_SUBSCRIPTIONS_ENABLED=false

# Restart server
# Result: Upgrade button hidden, /checkout returns 503
curl http://localhost:8000/subscription/checkout -H "..." 
# → {"detail": "Subscription service temporarily unavailable..."}
```

### Test 2: Disable Ads
```bash
# In .env
FEATURE_ADS_ENABLED=false

# Restart server  
# Result: Free users get unlimited queries (no ad token required)
# Try /chat endpoint - should work without X-Ad-Token header
```

### Test 3: Disable GTFS-RT
```bash
# In .env
FEATURE_GTFS_RT_ENABLED=false

# Restart server
# Result: Poller doesn't start, /nearby returns routes with no live data
```

### Test 4: Maintenance Mode
```bash
# In .env
MAINTENANCE_MODE=true

# Restart server
# Result: All non-essential features disabled
# Frontend shows maintenance banner
```

---

## Monitoring via Admin Endpoint

```bash
# As authenticated user, check system health
curl http://localhost:8000/config/admin/debug \
  -H "Authorization: Bearer <your-token>"

# Response example:
{
  "flags": {
    "subscriptions": true,
    "ads": false,
    "gtfs_rt": true,
    "auth": true,
    "rate_limiting": true,
    "database": true,
    "webhooks": false,
    "maintenance": false
  },
  "warnings": [
    "⚠️  Ads disabled - Free users get unlimited queries (no revenue)",
    "⚠️  Stripe webhooks disabled - Relying on polling for payment updates"
  ],
  "validation_ok": true,
  "maintenance_mode": false
}
```

---

## Priority Order (Recommended Implementation)

1. **HIGH PRIORITY** (Most impactful)
   - Phase 2: Subscriptions flag
   - Phase 3: Ads flag
   - Phase 4: GTFS-RT flag

2. **MEDIUM PRIORITY** (Important for testing)
   - Phase 5: Auth flag (for demo mode)
   - Phase 6: Rate limiting flag

3. **LOW PRIORITY** (Polish)
   - Phase 7: Frontend integration

---

## Rollback Procedure

If any feature causes problems in production:

1. **Immediate**: Edit `.env` and set feature flag to `false`
   ```bash
   FEATURE_SUBSCRIPTIONS_ENABLED=false
   ```

2. **Restart**: Restart application
   ```bash
   docker restart app  # or manual restart
   ```

3. **Verify**: Check admin endpoint for warnings
   ```bash
   curl http://localhost:8000/config/admin/debug -H "Authorization: Bearer ..."
   ```

4. **Communicate**: Users see graceful degradation message
   ```json
   {"detail": "Feature temporarily unavailable. Please try again later."}
   ```

5. **Debug**: With feature disabled, safely investigate issue
   
6. **Re-enable**: Once fixed, set flag back to `true` and restart

---

## Documentation in Code

Each flag check should include a comment:

```python
# 🚩 FEATURE FLAG: Check if subscriptions are enabled
if not FeatureFlags.SUBSCRIPTIONS_ENABLED:
    logger.warning("[checkout] Subscriptions disabled - returning 503")
    raise HTTPException(status_code=503, detail="...")
```

This makes it easy to find all flag checks via grep:
```bash
grep -r "# 🚩 FEATURE FLAG" transit-backend/
```

---

## Questions?

See FEATURE_FLAGS_PLAN.md for full documentation.

**Status**: Ready for Phase 2 implementation  
**Created**: 2026-05-09
