"""
app/models/settings.py
Three related but distinct concepts living in one file:

1. Setting — generic key-value store. Replaces the frontend's hardcoded
   FEATURES (sales_and_discounts, flash_deals_section, etc.) and
   BUSINESS_RULES (delivery_fee, mpesa_paybill, etc.) objects in
   mockData.ts. Once this is live, those become API-driven instead of
   hardcoded, which is what lets admin actually toggle them from
   SettingsPage.tsx.

2. HeroSlide — the homepage carousel slides, manageable from
   SettingsPage.tsx's "Homepage Hero Slides" section (the holiday/sale
   banner use case you specifically asked for).

3. AuditLog — tracks admin/store_manager actions for accountability.
   Already referenced by the Products routes we'll build (logs price
   changes, deletions, etc.) and flagged as a gap during frontend
   planning ("who changed this price and when").
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db


def _uuid():
    return str(uuid.uuid4())


class Setting(db.Model):
    __tablename__ = "settings"

    # Key is the primary key itself (e.g. "feature.sales_and_discounts",
    # "store.delivery_fee") rather than a separate UUID id — settings are
    # always looked up by key, never by a surrogate id.
    key = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text, nullable=False)  # stored as string; callers cast as needed

    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self):
        return f"<Setting {self.key}={self.value}>"


class HeroSlide(db.Model):
    __tablename__ = "hero_slides"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)

    title = db.Column(db.String(200), nullable=False)
    subtitle = db.Column(db.String(300), nullable=True)
    badge = db.Column(db.String(100), nullable=True)      # e.g. "🎉 Special Offer"
    cta = db.Column(db.String(50), nullable=False, default="Shop Now")
    cta_link = db.Column(db.String(200), nullable=False, default="/")

    image_url = db.Column(db.String(500), nullable=True)
    bg_gradient_from = db.Column(db.String(20), nullable=False, default="#1A5C38")
    bg_gradient_to = db.Column(db.String(20), nullable=False, default="#0f3b22")

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Serialization — matches frontend HeroSlide interface in SettingsPage.tsx
    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "subtitle": self.subtitle,
            "badge": self.badge,
            "cta": self.cta,
            "ctaLink": self.cta_link,
            "image": self.image_url,
            "bgFrom": self.bg_gradient_from,
            "bgTo": self.bg_gradient_to,
            "isActive": self.is_active,
        }

    def __repr__(self):
        return f"<HeroSlide {self.title}>"


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True, index=True)

    action = db.Column(db.String(100), nullable=False)        # e.g. "product.updated", "order.status_changed"
    resource_type = db.Column(db.String(50), nullable=False)  # e.g. "product", "order", "settings"
    resource_id = db.Column(db.String(36), nullable=True)

    details = db.Column(db.JSON, nullable=True)  # e.g. {"price": {"from": 450, "to": 500}}

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # ── Relationships ────────────────────────────────────────────────────────
    user = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "user": f"{self.user.first_name} {self.user.last_name}" if self.user else "System",
            "action": self.action,
            "resourceType": self.resource_type,
            "resourceId": self.resource_id,
            "details": self.details,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<AuditLog {self.action} by={self.user_id}>"