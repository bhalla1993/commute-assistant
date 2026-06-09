"""
Feature Flags & Configuration Management

This module provides centralized feature flag management. Each flag controls
whether a major use case is enabled or disabled. If disabled, the app gracefully
degrades (e.g., no subscriptions = free-only mode).

Flags are loaded from environment variables and available at startup/runtime.

Usage:
    from api.config import FeatureFlags
    
    if FeatureFlags.SUBSCRIPTIONS_ENABLED:
        # Payment system is on
    else:
        # Payment system is off - treat all users as free
"""

import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)


class FeatureFlags:
    """Centralized feature flag management for Commute Assistant"""
    
    # SUBSCRIPTIONS / STRIPE PAYMENTS
    # When disabled: All users free tier, no checkout, no premium features
    SUBSCRIPTIONS_ENABLED = os.getenv("FEATURE_SUBSCRIPTIONS_ENABLED", "true").lower() == "true"
    
    # ADS / AD-GATING SYSTEM
    # When disabled: Free users get unlimited queries (no 3-query limit), no ad tokens required
    ADS_ENABLED = os.getenv("FEATURE_ADS_ENABLED", "true").lower() == "true"
    
    # GTFS REAL-TIME DATA (TripUpdates, VehiclePositions, Alerts)
    # When disabled: Use static schedule only, no live delays/alerts
    GTFS_RT_ENABLED = os.getenv("FEATURE_GTFS_RT_ENABLED", "true").lower() == "true"
    
    # JWT AUTHENTICATION
    # When disabled: Anonymous access allowed, auto-login as "anonymous" user
    AUTH_ENABLED = os.getenv("FEATURE_AUTH_ENABLED", "true").lower() == "true"
    
    # RATE LIMITING (per-user, per-IP)
    # When disabled: No rate limits, good for testing/demo
    RATE_LIMITING_ENABLED = os.getenv("FEATURE_RATE_LIMITING_ENABLED", "true").lower() == "true"
    
    # DATABASE PERSISTENCE (SQLite)
    # When disabled: In-memory storage only (data lost on restart), good for demo mode
    DATABASE_ENABLED = os.getenv("FEATURE_DATABASE_ENABLED", "true").lower() == "true"
    
    # STRIPE WEBHOOK PROCESSING
    # When disabled: Webhooks endpoint exists but doesn't process events
    # Fallback: Polling mechanism becomes critical
    STRIPE_WEBHOOKS_ENABLED = os.getenv("FEATURE_STRIPE_WEBHOOKS_ENABLED", "true").lower() == "true"
    
    # MAINTENANCE MODE - EMERGENCY KILL SWITCH
    # When enabled: Disables ALL non-essential features, app runs in minimal mode
    # Use when critical system outage detected
    MAINTENANCE_MODE = os.getenv("MAINTENANCE_MODE", "false").lower() == "true"
    
    @classmethod
    def get_all(cls) -> Dict[str, bool]:
        """
        Return all feature flags as a dictionary.
        
        Maintenance mode takes priority - it disables all non-essential features.
        
        Returns:
            Dict[str, bool]: All flags with their current status
        """
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
    
    @classmethod
    def log_startup(cls) -> None:
        """
        Log all feature flags at application startup.
        Used for debugging and audit trail.
        """
        flags = cls.get_all()
        
        if cls.MAINTENANCE_MODE:
            logger.warning("🚨 MAINTENANCE MODE IS ENABLED - App running in minimal mode")
        
        logger.info("=" * 70)
        logger.info("FEATURE FLAGS STATUS:")
        logger.info("=" * 70)
        
        for flag_name, enabled in flags.items():
            status = "✅ ON " if enabled else "❌ OFF"
            logger.info(f"  {status} {flag_name.upper()}")
        
        logger.info("=" * 70)
    
    @classmethod
    def get_warnings(cls) -> list:
        """
        Return a list of warnings about disabled features.
        Useful for admin dashboards and monitoring.
        
        Returns:
            List of warning strings
        """
        warnings = []
        
        if cls.MAINTENANCE_MODE:
            warnings.append("⚠️  MAINTENANCE MODE ACTIVE - All non-essential features disabled")
        
        if not cls.SUBSCRIPTIONS_ENABLED:
            warnings.append("⚠️  Subscriptions disabled - All users have free-tier access")
        
        if not cls.ADS_ENABLED:
            warnings.append("⚠️  Ads disabled - Free users get unlimited queries (no revenue)")
        
        if not cls.GTFS_RT_ENABLED:
            warnings.append("⚠️  Live transit data disabled - Using static schedule only")
        
        if not cls.AUTH_ENABLED:
            warnings.append("⚠️  Authentication disabled - Anonymous access allowed (demo mode)")
        
        if not cls.RATE_LIMITING_ENABLED:
            warnings.append("⚠️  Rate limiting disabled - App vulnerable to DDoS")
        
        if not cls.DATABASE_ENABLED:
            warnings.append("⚠️  Database disabled - Using in-memory storage (data lost on restart)")
        
        if not cls.STRIPE_WEBHOOKS_ENABLED:
            warnings.append("⚠️  Stripe webhooks disabled - Relying on polling for payment updates")
        
        return warnings
    
    @classmethod
    def validate_config(cls) -> bool:
        """
        Validate feature flag configuration for conflicts.
        
        Returns:
            True if config is valid, False if conflicts detected
        """
        errors = []
        
        # If database is disabled, subscriptions don't make sense
        if not cls.DATABASE_ENABLED and cls.SUBSCRIPTIONS_ENABLED:
            errors.append("Cannot enable SUBSCRIPTIONS without DATABASE")
        
        # If database is disabled, auth doesn't make sense
        if not cls.DATABASE_ENABLED and cls.AUTH_ENABLED:
            errors.append("Cannot enable AUTH without DATABASE")
        
        if errors:
            logger.error("Feature flag configuration errors:")
            for error in errors:
                logger.error(f"  - {error}")
            return False
        
        return True


# Log flags on module import
logger.debug("[config] Feature flags module loaded")
