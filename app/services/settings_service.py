"""
app/services/settings_service.py
Helper to read/write the key-value Settings table. Replaces the frontend's
hardcoded FEATURES and BUSINESS_RULES constants in mockData.ts — once the
admin SettingsPage.tsx is wired to this, those become database-driven.

Cached in Redis for 60s since feature flags rarely change but get checked
on nearly every product/order request — avoids hitting Postgres constantly
for values that are almost always the same.
"""

import json
from app.extensions import db, redis_client
from app.models import Setting

SETTINGS_CACHE_KEY = "settings:all"
SETTINGS_CACHE_TTL = 60  # seconds

# Defaults — used as a fallback if a key is missing from the DB (e.g. before
# the first admin save, or if a new setting key is added to the codebase
# before a corresponding seed/migration creates the row).
DEFAULTS = {
    "feature.sales_and_discounts": "false",
    "feature.flash_deals_section": "false",
    "feature.free_delivery": "false",
    "feature.google_auth": "false",
    "feature.dynamic_hero": "false",
    "store.name": "I&G Warehouse",
    "store.address": "Industrial Area, Nairobi",
    "store.hours": "Mon–Sat, 8AM–6PM",
    "store.phone": "+254 700 123 456",
    "store.support_email": "support@iandg.co.ke",
    "store.delivery_fee": "200",
    "store.min_order_amount": "500",
    "store.mpesa_paybill": "000000",
    "store.mpesa_account_prefix": "ORDER",
    "store.free_delivery_threshold": "2000",
}


def _to_bool(value: str) -> bool:
    return str(value).lower() in ("true", "1", "yes")


def get_all_settings() -> dict:
    """Returns all settings as a flat {key: value} dict, Redis-cached."""
    if redis_client:
        cached = redis_client.get(SETTINGS_CACHE_KEY)
        if cached:
            return json.loads(cached)

    rows = Setting.query.all()
    settings = {row.key: row.value for row in rows}

    # Fill in any defaults not yet present in the DB
    for key, default_value in DEFAULTS.items():
        settings.setdefault(key, default_value)

    if redis_client:
        redis_client.set(SETTINGS_CACHE_KEY, json.dumps(settings), ex=SETTINGS_CACHE_TTL)

    return settings


def get_setting(key: str, default=None):
    settings = get_all_settings()
    return settings.get(key, default if default is not None else DEFAULTS.get(key))


def get_feature_flag(key: str) -> bool:
    """Usage: get_feature_flag('feature.sales_and_discounts')"""
    return _to_bool(get_setting(key, "false"))


def set_setting(key: str, value: str):
    """Update or create a setting, then invalidate the cache so the
    next read picks up the new value immediately."""
    row = Setting.query.get(key)
    if row:
        row.value = str(value)
    else:
        row = Setting(key=key, value=str(value))
        db.session.add(row)
    db.session.commit()

    if redis_client:
        redis_client.delete(SETTINGS_CACHE_KEY)


def invalidate_settings_cache():
    if redis_client:
        redis_client.delete(SETTINGS_CACHE_KEY)