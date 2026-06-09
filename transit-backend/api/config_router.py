"""
Configuration & Feature Flags API Endpoints

Routes:
  GET /config/flags         — All feature flags (for frontend)
  GET /admin/config/debug   — Detailed config + warnings (admin only)
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any

from api.config import FeatureFlags
from api.auth import get_current_user

router = APIRouter(prefix="/config", tags=["configuration"])


@router.get("/flags", summary="Get all feature flags")
def get_feature_flags() -> Dict[str, bool]:
    """
    Returns all feature flags for the frontend to adapt UI accordingly.
    
    Example response:
    {
      "subscriptions": true,
      "ads": true,
      "gtfs_rt": true,
      "auth": true,
      "rate_limiting": true,
      "database": true,
      "webhooks": true,
      "maintenance": false
    }
    
    When a flag is false, the corresponding feature is disabled:
    - subscriptions=false → Hide upgrade button, all users are free
    - ads=false → No ad units, unlimited queries for free users
    - gtfs_rt=false → No live data, schedule-only mode
    - etc.
    """
    return FeatureFlags.get_all()


@router.get("/admin/debug", summary="Admin: Detailed config debug info")
def get_admin_config(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """
    Returns detailed configuration info with warnings.
    
    Requires authentication. In production, should be admin-only.
    
    Example response:
    {
      "flags": {...},
      "warnings": [
        "⚠️  Ads disabled - Free users get unlimited queries",
        "⚠️  Webhooks disabled - Relying on polling"
      ],
      "validation_ok": true,
      "environment": "local"
    }
    """
    return {
        "flags": FeatureFlags.get_all(),
        "warnings": FeatureFlags.get_warnings(),
        "validation_ok": FeatureFlags.validate_config(),
        "maintenance_mode": FeatureFlags.MAINTENANCE_MODE,
        "subscriptions_enabled": FeatureFlags.SUBSCRIPTIONS_ENABLED,
        "ads_enabled": FeatureFlags.ADS_ENABLED,
        "gtfs_rt_enabled": FeatureFlags.GTFS_RT_ENABLED,
        "auth_enabled": FeatureFlags.AUTH_ENABLED,
        "rate_limiting_enabled": FeatureFlags.RATE_LIMITING_ENABLED,
        "database_enabled": FeatureFlags.DATABASE_ENABLED,
        "webhooks_enabled": FeatureFlags.STRIPE_WEBHOOKS_ENABLED,
    }
