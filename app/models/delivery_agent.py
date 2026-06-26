"""
app/models/delivery_agent.py
DeliveryAgent — extends a User (role='delivery_agent') with agent-specific
fields. Matches the frontend AgentManagement.tsx Agent interface exactly.

Design note: agent-specific data (vehicle, ID number, status) lives in its
own table rather than bolted onto User, since those fields are meaningless
for customers/admin/store_manager. The 1:1 link to User is what creates
their actual login account — this is the mechanism that closes the gap
flagged during frontend planning ("how does someone become a delivery_agent").
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db

VEHICLE_TYPES = ["motorcycle", "bicycle", "car", "on_foot"]
AGENT_STATUSES = ["available", "busy", "offline"]


def _uuid():
    return str(uuid.uuid4())


class DeliveryAgent(db.Model):
    __tablename__ = "delivery_agents"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False, unique=True)

    vehicle_type = db.Column(db.String(20), nullable=False, default="motorcycle")
    id_number = db.Column(db.String(30), nullable=False)  # National ID

    # available | busy | offline — admin-managed availability,
    # matches AgentManagement.tsx AGENT_STATUS_CONFIG
    status = db.Column(db.String(20), nullable=False, default="offline")

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    user = db.relationship("User", back_populates="delivery_agent_profile")
    assigned_orders = db.relationship("Order", back_populates="assigned_agent")

    # ── Computed properties ──────────────────────────────────────────────────
    @property
    def active_delivery_count(self) -> int:
        """Orders currently assigned to this agent that aren't delivered yet —
        matches the 'activeDeliveries' count shown in AgentManagement.tsx
        and the DeliveryManagementPage agent panel."""
        return sum(
            1 for order in self.assigned_orders
            if order.status in ("assigned", "out_for_delivery", "processing")
        )

    # ── Serialization — matches frontend Agent interface ─────────────────────
    def to_dict(self):
        return {
            "id": self.id,
            "name": f"{self.user.first_name} {self.user.last_name}" if self.user else None,
            "phone": self.user.phone if self.user else None,
            "email": self.user.email if self.user else None,
            "vehicleType": self.vehicle_type,
            "idNumber": self.id_number,
            "status": self.status,
            "isActive": self.is_active,
            "activeDeliveries": self.active_delivery_count,
            "joinedAt": self.created_at.date().isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<DeliveryAgent {self.id} status={self.status}>"