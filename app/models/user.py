"""
app/models/user.py
Single User table for all roles: customer, admin, store_manager, delivery_agent.
"""

import uuid
from datetime import datetime, timezone
import bcrypt
from app.extensions import db


def _uuid():
    return str(uuid.uuid4())


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)

    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    phone = db.Column(db.String(20), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # customer | admin | store_manager | delivery_agent
    role = db.Column(db.String(20), nullable=False, default="customer", index=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # DPA 2019 consent tracking — recorded at registration time
    agreed_to_terms = db.Column(db.Boolean, default=False, nullable=False)
    agreed_to_terms_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    orders = db.relationship("Order", back_populates="customer", foreign_keys="Order.customer_id")
    delivery_agent_profile = db.relationship(
        "DeliveryAgent", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    # ── Password helpers ─────────────────────────────────────────────────────
    def set_password(self, raw_password: str):
        self.password_hash = bcrypt.hashpw(
            raw_password.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")

    def check_password(self, raw_password: str) -> bool:
        return bcrypt.checkpw(
            raw_password.encode("utf-8"), self.password_hash.encode("utf-8")
        )

    # ── Role helpers ─────────────────────────────────────────────────────────
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_store_manager(self) -> bool:
        return self.role == "store_manager"

    @property
    def is_delivery_agent(self) -> bool:
        return self.role == "delivery_agent"

    @property
    def is_customer(self) -> bool:
        return self.role == "customer"

    @property
    def is_staff(self) -> bool:
        """Admin or store_manager — matches frontend's isBackendUser logic
        minus delivery_agent, which has its own separate dashboard."""
        return self.role in ("admin", "store_manager")

    # ── Serialization — matches frontend User interface (camelCase) ─────────
    def to_dict(self, include_sensitive=False):
        data = {
            "id": self.id,
            "firstName": self.first_name,
            "lastName": self.last_name,
            "email": self.email,
            "phone": self.phone,
            "role": self.role,
            "isActive": self.is_active,
        }
        if include_sensitive:
            data["agreedToTerms"] = self.agreed_to_terms
            data["agreedToTermsAt"] = (
                self.agreed_to_terms_at.isoformat() if self.agreed_to_terms_at else None
            )
            data["createdAt"] = self.created_at.isoformat() if self.created_at else None
        return data

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"