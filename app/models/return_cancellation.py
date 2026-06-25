"""
app/models/return_cancellation.py
CancellationRequest and ReturnRequest — matches the two request flows built
into the customer OrdersPage.tsx and reviewed/actioned in admin OrdersPage.tsx.

CancellationRequest:
    Created when a customer tries to cancel an order that's already past
    'pending' status (i.e. instant cancel isn't available — see
    Order.to_customer_dict()'s canCancelInstantly). Admin reviews and either
    approves (order -> cancelled) or declines (order -> back to processing).

ReturnRequest:
    Created when a customer requests a return on a 'delivered' order within
    the 7-day window. Matches the RETURN_REASONS list in OrdersPage.tsx
    exactly. Admin approves (triggers refund) or declines.
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db

RETURN_REASONS = [
    "Item damaged or broken",
    "Item expired or near expiry",
    "Wrong item delivered",
    "Item missing from order",
    "Quality not as expected",
    "Other",
]

REQUEST_STATUSES = ["pending_review", "approved", "declined"]


def _uuid():
    return str(uuid.uuid4())


class CancellationRequest(db.Model):
    __tablename__ = "cancellation_requests"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    order_id = db.Column(db.String(20), db.ForeignKey("orders.id"), nullable=False, unique=True)

    reason = db.Column(db.Text, nullable=True)  # optional — matches frontend's optional textarea
    status = db.Column(db.String(20), nullable=False, default="pending_review")

    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    order = db.relationship("Order", back_populates="cancellation_request")
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])

    def to_dict(self):
        return {
            "reason": self.reason,
            "status": self.status,
            "requestedAt": self.requested_at.isoformat() if self.requested_at else None,
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    def __repr__(self):
        return f"<CancellationRequest order={self.order_id} status={self.status}>"


class ReturnRequest(db.Model):
    __tablename__ = "return_requests"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    order_id = db.Column(db.String(20), db.ForeignKey("orders.id"), nullable=False, unique=True)

    # One of RETURN_REASONS — validated at the schema layer, not enforced
    # at the DB level, so the list can be extended without a migration.
    reason = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text, nullable=True)  # optional extra description

    status = db.Column(db.String(20), nullable=False, default="pending_review")

    requested_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    resolved_at = db.Column(db.DateTime, nullable=True)
    resolved_by_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=True)

    # Set once a refund has actually been initiated via Pesapal/iPay/Daraja —
    # separate from `status` because "approved" and "refund actually sent"
    # can be two different moments (the refund call to the payment gateway
    # might fail and need a retry even after admin has approved it).
    refund_initiated_at = db.Column(db.DateTime, nullable=True)
    refund_reference = db.Column(db.String(100), nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    order = db.relationship("Order", back_populates="return_request")
    resolved_by = db.relationship("User", foreign_keys=[resolved_by_id])

    def to_dict(self):
        return {
            "reason": self.reason,
            "details": self.details,
            "status": self.status,
            "requestedAt": self.requested_at.isoformat() if self.requested_at else None,
            "resolvedAt": self.resolved_at.isoformat() if self.resolved_at else None,
        }

    def __repr__(self):
        return f"<ReturnRequest order={self.order_id} status={self.status}>"