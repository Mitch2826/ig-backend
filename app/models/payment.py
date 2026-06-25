"""
app/models/payment.py
Payment — tracks every payment transaction attempt, both collections
(customer paying for an order) and refunds (return request approved).

This is what powers the admin ReportsPage.tsx payment method breakdown
and the reconciliation note pointing to the Safaricom Business Portal /
iPay Dashboard. Every Daraja STK Push and iPay card transaction gets a
row here, regardless of success/failure, so nothing is ever silently lost.

One order can have multiple Payment rows over its lifetime:
  - the original collection (type='collection')
  - a refund if a return was approved (type='refund')
  - a retry if the first collection attempt timed out/failed
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db

PAYMENT_METHODS = ["mpesa", "debit_card"]
PAYMENT_TYPES = ["collection", "refund"]
PAYMENT_STATUSES = ["pending", "completed", "failed", "timeout"]


def _uuid():
    return str(uuid.uuid4())


class Payment(db.Model):
    __tablename__ = "payments"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    order_id = db.Column(db.String(20), db.ForeignKey("orders.id"), nullable=False, index=True)

    method = db.Column(db.String(20), nullable=False)        # mpesa | debit_card
    type = db.Column(db.String(20), nullable=False, default="collection")  # collection | refund
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)

    amount = db.Column(db.Numeric(10, 2), nullable=False)

    # ── M-Pesa specific (Daraja) ─────────────────────────────────────────────
    mpesa_phone = db.Column(db.String(20), nullable=True)
    mpesa_checkout_request_id = db.Column(db.String(100), nullable=True)  # from STK Push initiation
    mpesa_receipt_number = db.Column(db.String(50), nullable=True)        # e.g. "QJK7ABC123" — confirmed via callback

    # ── Card specific (iPay/Pesapal) ─────────────────────────────────────────
    card_transaction_ref = db.Column(db.String(100), nullable=True)

    # ── Generic reference — whichever of the above applies, mirrored here
    # so the rest of the app (e.g. Order.payment_reference) doesn't need to
    # know which gateway was used ────────────────────────────────────────────
    reference = db.Column(db.String(100), nullable=True, index=True)

    # Raw callback payload from the gateway, stored for debugging/audit —
    # if a payment dispute ever comes up, this is the source of truth
    gateway_response = db.Column(db.JSON, nullable=True)

    failure_reason = db.Column(db.String(255), nullable=True)

    initiated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    order = db.relationship("Order", back_populates="payments")

    def to_dict(self):
        return {
            "id": self.id,
            "orderId": self.order_id,
            "method": self.method,
            "type": self.type,
            "status": self.status,
            "amount": float(self.amount),
            "reference": self.reference,
            "mpesaReceiptNumber": self.mpesa_receipt_number,
            "cardTransactionRef": self.card_transaction_ref,
            "failureReason": self.failure_reason,
            "initiatedAt": self.initiated_at.isoformat() if self.initiated_at else None,
            "completedAt": self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f"<Payment {self.id} {self.method} {self.status} {self.amount}>"