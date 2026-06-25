"""
app/models/order.py
Order and OrderItem — matches the frontend AdminOrder / MyOrder interfaces
exactly, including the order state machine, cancellation requests, and
return requests built into CheckoutPage, OrdersPage, and admin OrdersPage.

State machine (matches STATUS_CONFIG.next in the frontend):
    pending                 -> processing, cancelled
    processing              -> out_for_delivery, cancelled
    out_for_delivery        -> delivered
    delivered               -> (terminal)
    cancelled               -> (terminal)
    cancellation_requested  -> cancelled, processing  (admin approves/declines)

VALID_TRANSITIONS below is the single source of truth for this — enforced
in the Orders blueprint, not here, so the model itself stays a plain
data container. Defined here so it's co-located with the statuses it governs.
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db

ORDER_STATUSES = [
    "pending", "processing", "out_for_delivery",
    "delivered", "cancelled", "cancellation_requested",
]

VALID_TRANSITIONS = {
    "pending": ["processing", "cancelled"],
    "processing": ["out_for_delivery", "cancelled"],
    "out_for_delivery": ["delivered"],
    "delivered": [],
    "cancelled": [],
    "cancellation_requested": ["cancelled", "processing"],
}

PAYMENT_METHODS = ["mpesa", "debit_card"]
FULFILMENT_TYPES = ["delivery", "pickup"]


def _uuid():
    return str(uuid.uuid4())


def _order_number():
    """Generates an order ID like ORD-AX7K2M, matching the frontend's
    mock order ID format used throughout OrderConfirmationPage etc."""
    import random
    import string
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"ORD-{suffix}"


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.String(20), primary_key=True, default=_order_number)
    customer_id = db.Column(db.String(36), db.ForeignKey("users.id"), nullable=False)

    # ── Pricing snapshot — stored at order time, never recalculated later,
    # so historical orders stay accurate even if product prices change after ──
    subtotal = db.Column(db.Numeric(10, 2), nullable=False)
    delivery_fee = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(10, 2), nullable=False)

    status = db.Column(db.String(30), nullable=False, default="pending", index=True)

    fulfilment_type = db.Column(db.String(20), nullable=False)  # delivery | pickup

    # ── Delivery address — only populated when fulfilment_type == "delivery" ──
    delivery_zone = db.Column(db.String(100), nullable=True)
    delivery_estate = db.Column(db.String(120), nullable=True)
    delivery_street = db.Column(db.String(200), nullable=True)
    delivery_building = db.Column(db.String(120), nullable=True)
    delivery_instructions = db.Column(db.Text, nullable=True)

    # ── Contact snapshot — stored at order time (customer details could
    # change later on their account; the order should keep what was used then) ──
    contact_first_name = db.Column(db.String(80), nullable=False)
    contact_last_name = db.Column(db.String(80), nullable=False)
    contact_phone = db.Column(db.String(20), nullable=False)
    contact_email = db.Column(db.String(255), nullable=False)

    # ── Payment ──────────────────────────────────────────────────────────────
    payment_method = db.Column(db.String(20), nullable=False)  # mpesa | debit_card
    payment_reference = db.Column(db.String(100), nullable=True)  # M-Pesa code or card txn ref
    payment_confirmed_at = db.Column(db.DateTime, nullable=True)

    # ── Delivery assignment ──────────────────────────────────────────────────
    assigned_agent_id = db.Column(db.String(36), db.ForeignKey("delivery_agents.id"), nullable=True)
    delivered_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    customer = db.relationship("User", back_populates="orders", foreign_keys=[customer_id])
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    assigned_agent = db.relationship("DeliveryAgent", back_populates="assigned_orders")
    cancellation_request = db.relationship(
        "CancellationRequest", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )
    return_request = db.relationship(
        "ReturnRequest", back_populates="order", uselist=False, cascade="all, delete-orphan"
    )
    payments = db.relationship("Payment", back_populates="order", cascade="all, delete-orphan")

    # ── State machine helper ─────────────────────────────────────────────────
    def can_transition_to(self, new_status: str) -> bool:
        return new_status in VALID_TRANSITIONS.get(self.status, [])

    # ── Serialization — matches frontend AdminOrder interface ───────────────
    def to_dict(self, for_admin=True):
        data = {
            "id": self.id,
            "customer": {
                "name": f"{self.contact_first_name} {self.contact_last_name}",
                "phone": self.contact_phone,
                "email": self.contact_email,
            },
            "items": [item.to_dict() for item in self.items],
            "subtotal": float(self.subtotal),
            "deliveryFee": float(self.delivery_fee),
            "total": float(self.total),
            "status": self.status,
            "paymentMethod": self.payment_method,
            "paymentReference": self.payment_reference,
            "fulfilmentType": self.fulfilment_type,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "updatedAt": self.updated_at.isoformat() if self.updated_at else None,
        }

        if self.fulfilment_type == "delivery":
            data["deliveryAddress"] = {
                "zone": self.delivery_zone,
                "estate": self.delivery_estate,
                "street": self.delivery_street,
                "building": self.delivery_building,
                "instructions": self.delivery_instructions,
            }

        if self.assigned_agent:
            data["assignedAgent"] = self.assigned_agent.user.first_name + " " + self.assigned_agent.user.last_name

        if self.return_request:
            data["returnRequest"] = self.return_request.to_dict()

        return data

    def to_customer_dict(self):
        """Slimmer shape for the customer-facing OrdersPage — matches
        the frontend MyOrder interface (no internal admin-only fields)."""
        return {
            "id": self.id,
            "items": [item.to_dict() for item in self.items],
            "subtotal": float(self.subtotal),
            "deliveryFee": float(self.delivery_fee),
            "total": float(self.total),
            "status": self.status,
            "createdAt": self.created_at.isoformat() if self.created_at else None,
            "deliveredAt": self.delivered_at.isoformat() if self.delivered_at else None,
            "canCancelInstantly": self.status == "pending",
            "hasReturnRequest": self.return_request is not None,
            "fulfilmentType": self.fulfilment_type,
            "paymentMethod": self.payment_method,
            "paymentReference": self.payment_reference,
        }

    def __repr__(self):
        return f"<Order {self.id} {self.status}>"


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    order_id = db.Column(db.String(20), db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.String(36), db.ForeignKey("products.id"), nullable=False)

    quantity = db.Column(db.Integer, nullable=False)
    # Price snapshot at time of order — never recalculated, same reasoning
    # as Order.subtotal/total above.
    price = db.Column(db.Numeric(10, 2), nullable=False)

    # ── Relationships ────────────────────────────────────────────────────────
    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")

    def to_dict(self):
        return {
            "productId": self.product_id,
            "quantity": self.quantity,
            "price": float(self.price),
            # Enriched product fields for display — frontend's enrichItems()
            # currently does this client-side by looking up mockData.products;
            # once this is live we send it pre-enriched so the frontend can
            # eventually drop that lookup.
            "name": self.product.name if self.product else None,
            "unit": self.product.unit if self.product else None,
            "image": self.product.primary_image_url if self.product else None,
        }

    def __repr__(self):
        return f"<OrderItem order={self.order_id} product={self.product_id} qty={self.quantity}>"