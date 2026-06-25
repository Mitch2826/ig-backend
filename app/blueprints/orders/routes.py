"""
app/blueprints/orders/routes.py
Order lifecycle endpoints.

Customer endpoints:
    POST   /api/orders/                    place a new order
    GET    /api/orders/                     own order history
    GET    /api/orders/<id>                  own single order detail
    PATCH  /api/orders/<id>/cancel            instant cancel (only while pending)
    POST   /api/orders/<id>/cancellation-request   request cancel (processing/out_for_delivery)
    POST   /api/orders/<id>/return-request    request a return (delivered, within 7 days)

Admin/store_manager endpoints:
    GET    /api/orders/admin/all             list all orders with filters
    GET    /api/orders/admin/<id>             single order detail (admin shape)
    PATCH  /api/orders/admin/<id>/status       update order status (state machine enforced)
    PATCH  /api/orders/admin/<id>/return-request   approve/decline a return
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models import Order, OrderItem, Product, User, CancellationRequest, ReturnRequest
from app.models.order import VALID_TRANSITIONS
from app.utils.decorators import staff_only, customer_only
from app.services.settings_service import get_setting, get_feature_flag
from app.services.inventory_service import reserve_stock, release_reservation, InsufficientStockError
from app.services.email_service import send_order_confirmation_email, send_order_status_update_email
from app.services.sms_service import send_order_confirmation_sms, send_order_status_update_sms
from app.blueprints.orders.schemas import (
    PlaceOrderSchema, OrderResponseSchema, MyOrderResponseSchema, OrderListResponseSchema,
    OrderListQuerySchema, StatusUpdateSchema, CancellationRequestSchema,
    ReturnRequestCreateSchema, ReturnResolveSchema, MessageSchema,
)

blp = Blueprint("orders", __name__, url_prefix="/api/orders", description="Orders")


RETURN_WINDOW_DAYS = 7


def _within_return_window(delivered_at) -> bool:
    if not delivered_at:
        return False
    days = (datetime.now(timezone.utc) - delivered_at).days
    return days <= RETURN_WINDOW_DAYS


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/orders/  — place a new order
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/")
class PlaceOrder(MethodView):
    @jwt_required()
    @customer_only
    @blp.arguments(PlaceOrderSchema)
    @blp.response(201, MyOrderResponseSchema)
    def post(self, data):
        customer_id = get_jwt_identity()

        # ── Validate products and quantities, build line items ──────────────
        line_items = []  # [{"product": Product, "quantity": int}]
        subtotal = 0

        for item_input in data["items"]:
            product = Product.query.get(item_input["productId"])
            if not product or not product.is_active:
                abort(400, message=f"Product {item_input['productId']} is not available")

            quantity = item_input["quantity"]
            line_items.append({"product": product, "quantity": quantity})
            subtotal += float(product.effective_price) * quantity

        # ── Minimum order check ──────────────────────────────────────────────
        min_order = float(get_setting("store.min_order_amount", "500"))
        if subtotal < min_order:
            abort(400, message=f"Minimum order amount is KES {min_order:.0f}")

        # ── Reserve stock — raises InsufficientStockError if anything is short.
        # This happens BEFORE we create the order, in the same transaction,
        # so if it fails nothing is left half-created. ──────────────────────
        try:
            reserve_stock(line_items)
        except InsufficientStockError as e:
            db.session.rollback()
            abort(400, message=str(e))

        # ── Delivery fee ──────────────────────────────────────────────────────
        delivery_fee = 0
        if data["fulfilmentType"] == "delivery":
            delivery_fee = float(get_setting("store.delivery_fee", "200"))
            if get_feature_flag("feature.free_delivery"):
                threshold = float(get_setting("store.free_delivery_threshold", "2000"))
                if subtotal >= threshold:
                    delivery_fee = 0

        total = subtotal + delivery_fee

        # ── Create order ──────────────────────────────────────────────────────
        order = Order(
            customer_id=customer_id,
            subtotal=subtotal, delivery_fee=delivery_fee, total=total,
            status="pending",
            fulfilment_type=data["fulfilmentType"],
            delivery_zone=data.get("zone"), delivery_estate=data.get("estate"),
            delivery_street=data.get("street"), delivery_building=data.get("buildingApartment"),
            delivery_instructions=data.get("deliveryInstructions"),
            contact_first_name=data["firstName"], contact_last_name=data["lastName"],
            contact_phone=data["phone"], contact_email=data["email"],
            payment_method=data["paymentMethod"],
        )
        db.session.add(order)
        db.session.flush()  # get order.id before adding items

        for line in line_items:
            db.session.add(OrderItem(
                order_id=order.id, product_id=line["product"].id,
                quantity=line["quantity"], price=line["product"].effective_price,
            ))

        db.session.commit()

        # Fire-and-forget notifications — failures here never block the
        # order itself (both functions catch their own exceptions and
        # return False rather than raising)
        send_order_confirmation_email(order)
        send_order_confirmation_sms(order)

        # NOTE: payment is NOT processed here — that happens via the
        # Payments blueprint (Phase 3), which the frontend calls right
        # after this endpoint returns, passing this order's id. Stock
        # stays "reserved" (not yet deducted) until that payment confirms.

        return order.to_customer_dict()


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/orders/  — customer's own order history
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/")
class MyOrders(MethodView):
    @jwt_required()
    @customer_only
    @blp.response(200, MyOrderResponseSchema(many=True))
    def get(self):
        customer_id = get_jwt_identity()
        orders = (
            Order.query.filter_by(customer_id=customer_id)
            .order_by(Order.created_at.desc())
            .all()
        )
        return [o.to_customer_dict() for o in orders]


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/orders/<id>  — customer's own single order
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:order_id>")
class MyOrderDetail(MethodView):
    @jwt_required()
    @customer_only
    @blp.response(200, MyOrderResponseSchema)
    def get(self, order_id):
        customer_id = get_jwt_identity()
        order = Order.query.filter_by(id=order_id, customer_id=customer_id).first()
        if not order:
            abort(404, message="Order not found")
        return order.to_customer_dict()


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/orders/<id>/cancel  — instant cancel (only while pending)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:order_id>/cancel")
class InstantCancel(MethodView):
    @jwt_required()
    @customer_only
    @blp.arguments(CancellationRequestSchema)
    @blp.response(200, MyOrderResponseSchema)
    def patch(self, data, order_id):
        customer_id = get_jwt_identity()
        order = Order.query.filter_by(id=order_id, customer_id=customer_id).first()
        if not order:
            abort(404, message="Order not found")

        if order.status != "pending":
            abort(
                400,
                message="This order can no longer be cancelled instantly. "
                        "Submit a cancellation request instead.",
            )

        items = [{"product": item.product, "quantity": item.quantity} for item in order.items]
        release_reservation(items)

        order.status = "cancelled"
        db.session.commit()

        return order.to_customer_dict()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/orders/<id>/cancellation-request — request cancel (processing/out_for_delivery)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:order_id>/cancellation-request")
class CreateCancellationRequest(MethodView):
    @jwt_required()
    @customer_only
    @blp.arguments(CancellationRequestSchema)
    @blp.response(200, MyOrderResponseSchema)
    def post(self, data, order_id):
        customer_id = get_jwt_identity()
        order = Order.query.filter_by(id=order_id, customer_id=customer_id).first()
        if not order:
            abort(404, message="Order not found")

        if order.status not in ("processing", "out_for_delivery"):
            abort(400, message="A cancellation request isn't applicable for this order's current status")

        if order.cancellation_request:
            abort(409, message="A cancellation request has already been submitted for this order")

        db.session.add(CancellationRequest(order_id=order.id, reason=data.get("reason")))
        order.status = "cancellation_requested"
        db.session.commit()

        return order.to_customer_dict()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/orders/<id>/return-request — request a return (delivered, within 7 days)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:order_id>/return-request")
class CreateReturnRequest(MethodView):
    @jwt_required()
    @customer_only
    @blp.arguments(ReturnRequestCreateSchema)
    @blp.response(200, MyOrderResponseSchema)
    def post(self, data, order_id):
        customer_id = get_jwt_identity()
        order = Order.query.filter_by(id=order_id, customer_id=customer_id).first()
        if not order:
            abort(404, message="Order not found")

        if order.status != "delivered":
            abort(400, message="Returns can only be requested for delivered orders")

        if not _within_return_window(order.delivered_at):
            abort(400, message=f"The {RETURN_WINDOW_DAYS}-day return window for this order has passed")

        if order.return_request:
            abort(409, message="A return request has already been submitted for this order")

        db.session.add(ReturnRequest(
            order_id=order.id, reason=data["reason"], details=data.get("details"),
        ))
        db.session.commit()

        return order.to_customer_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Admin — list all orders with filters
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/all")
class AdminOrderList(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(OrderListQuerySchema, location="query")
    @blp.response(200, OrderListResponseSchema)
    def get(self, args):
        query = Order.query

        if args["status"] != "all":
            query = query.filter(Order.status == args["status"])

        if args["paymentMethod"] != "all":
            query = query.filter(Order.payment_method == args["paymentMethod"])

        if args["search"]:
            term = f"%{args['search']}%"
            query = query.join(User, Order.customer_id == User.id, isouter=True).filter(
                or_(
                    Order.id.ilike(term),
                    Order.contact_first_name.ilike(term),
                    Order.contact_last_name.ilike(term),
                    Order.contact_phone.ilike(term),
                    Order.payment_reference.ilike(term),
                )
            )

        query = query.order_by(Order.created_at.desc())

        total = query.count()
        page_items = (
            query.offset((args["page"] - 1) * args["perPage"])
            .limit(args["perPage"])
            .all()
        )

        return {
            "items": [o.to_dict() for o in page_items],
            "total": total,
            "page": args["page"],
            "perPage": args["perPage"],
            "totalPages": max(1, (total + args["perPage"] - 1) // args["perPage"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Admin — single order detail
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:order_id>")
class AdminOrderDetail(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, OrderResponseSchema)
    def get(self, order_id):
        order = Order.query.get(order_id)
        if not order:
            abort(404, message="Order not found")
        return order.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Admin — update status (state machine enforced)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:order_id>/status")
class AdminUpdateStatus(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(StatusUpdateSchema)
    @blp.response(200, OrderResponseSchema)
    def patch(self, data, order_id):
        order = Order.query.get(order_id)
        if not order:
            abort(404, message="Order not found")

        new_status = data["status"]

        if not order.can_transition_to(new_status):
            valid = VALID_TRANSITIONS.get(order.status, [])
            abort(
                400,
                message=f"Cannot transition from '{order.status}' to '{new_status}'. "
                        f"Valid next states: {valid or 'none (terminal status)'}",
            )

        items = [{"product": item.product, "quantity": item.quantity} for item in order.items]

        # ── Side effects of specific transitions ─────────────────────────────
        if new_status == "cancelled":
            # Whether cancelling from pending/processing directly, or approving
            # a cancellation_requested order — release the reserved stock.
            release_reservation(items)
            if order.cancellation_request:
                order.cancellation_request.status = "approved" if order.status == "cancellation_requested" else order.cancellation_request.status
                order.cancellation_request.resolved_at = datetime.now(timezone.utc)

        elif new_status == "processing" and order.status == "cancellation_requested":
            # Admin declined the cancellation request — order continues
            if order.cancellation_request:
                order.cancellation_request.status = "declined"
                order.cancellation_request.resolved_at = datetime.now(timezone.utc)

        elif new_status == "delivered":
            order.delivered_at = datetime.now(timezone.utc)

        order.status = new_status
        db.session.commit()

        # Notify customer of status changes they actually care about
        # (skip "processing" from cancellation_requested decline — that's
        # not really news to them, they just stay in the queue)
        if new_status in ("out_for_delivery", "delivered", "cancelled"):
            send_order_status_update_email(order)
            send_order_status_update_sms(order)

        return order.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Admin — approve/decline a return request
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:order_id>/return-request")
class AdminResolveReturn(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(ReturnResolveSchema)
    @blp.response(200, OrderResponseSchema)
    def patch(self, data, order_id):
        order = Order.query.get(order_id)
        if not order:
            abort(404, message="Order not found")

        if not order.return_request:
            abort(404, message="No return request exists for this order")

        if order.return_request.status != "pending_review":
            abort(400, message=f"This return request has already been {order.return_request.status}")

        order.return_request.status = data["status"]
        order.return_request.resolved_at = datetime.now(timezone.utc)
        order.return_request.resolved_by_id = get_jwt_identity()

        # NOTE: actually initiating the refund via Pesapal/iPay/Daraja
        # happens in the Payments blueprint (Phase 3) — this endpoint just
        # records admin's decision. return_request.refund_initiated_at and
        # refund_reference get set there once the gateway call succeeds.

        db.session.commit()
        return order.to_dict()