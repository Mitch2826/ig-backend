"""
app/blueprints/payments/routes.py
Payment initiation and callback handling.

Customer endpoints:
    POST /api/payments/mpesa/initiate    trigger STK Push for an order
    GET  /api/payments/<id>/status        poll payment status (frontend polls
                                            this while waiting for the customer
                                            to enter their M-Pesa PIN)

Safaricom calls this endpoint directly (no auth — Safaricom doesn't send
our JWT, this is a public webhook secured only by being an unguessable
URL plus Daraja's own IP allowlisting on their end):
    POST /api/payments/mpesa/callback

Card payments (iPay/Pesapal) follow the same pattern but aren't built yet —
placeholder noted below for Phase 3 continuation.
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
import requests as requests_lib

from app.extensions import db
from app.models import Order, Payment
from app.utils.decorators import customer_only
from app.services.daraja_service import initiate_stk_push, parse_callback
from app.services.inventory_service import confirm_reservation, release_reservation
from app.services.email_service import send_order_status_update_email
from app.services.sms_service import send_order_status_update_sms
from app.blueprints.payments.schemas import (
    InitiateMpesaPaymentSchema, InitiateMpesaResponseSchema,
    PaymentResponseSchema, MessageSchema,
)

blp = Blueprint("payments", __name__, url_prefix="/api/payments", description="Payments")


def _normalize_phone(phone: str) -> str:
    """Daraja requires format 254712345678 - no +, no leading 0."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("+"):
        phone = phone[1:]
    if phone.startswith("0"):
        phone = "254" + phone[1:]
    if not phone.startswith("254"):
        phone = "254" + phone
    return phone


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/payments/mpesa/initiate
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/mpesa/initiate")
class InitiateMpesaPayment(MethodView):
    @jwt_required()
    @customer_only
    @blp.arguments(InitiateMpesaPaymentSchema)
    @blp.response(201, InitiateMpesaResponseSchema)
    def post(self, data):
        customer_id = get_jwt_identity()
        order = Order.query.filter_by(id=data["orderId"], customer_id=customer_id).first()
        if not order:
            abort(404, message="Order not found")

        if order.status != "pending":
            abort(400, message="This order is not awaiting payment")

        if order.payment_method != "mpesa":
            abort(400, message="This order was not set up for M-Pesa payment")

        phone = _normalize_phone(data["phone"])

        # Create the Payment record BEFORE calling Daraja, status=pending —
        # so even if the STK push call itself fails, we have a record of
        # the attempt rather than losing it silently.
        payment = Payment(
            order_id=order.id, method="mpesa", type="collection",
            status="pending", amount=order.total, mpesa_phone=phone,
        )
        db.session.add(payment)
        db.session.flush()

        try:
            daraja_response = initiate_stk_push(phone, float(order.total), order.id)
        except requests_lib.HTTPError as e:
            payment.status = "failed"
            payment.failure_reason = f"Daraja request rejected: {str(e)}"
            db.session.commit()
            abort(502, message="Unable to initiate M-Pesa payment. Please try again.")
        except requests_lib.RequestException as e:
            payment.status = "failed"
            payment.failure_reason = f"Network error contacting Daraja: {str(e)}"
            db.session.commit()
            abort(502, message="Unable to reach M-Pesa right now. Please try again shortly.")

        # ResponseCode "0" means Daraja accepted the request and is sending
        # the prompt — it does NOT mean the customer has paid yet. That
        # confirmation only comes via the callback.
        if daraja_response.get("ResponseCode") != "0":
            payment.status = "failed"
            payment.failure_reason = daraja_response.get("ResponseDescription", "Unknown Daraja error")
            db.session.commit()
            abort(502, message=daraja_response.get("ResponseDescription", "Payment request failed"))

        payment.mpesa_checkout_request_id = daraja_response.get("CheckoutRequestID")
        payment.gateway_response = daraja_response
        db.session.commit()

        return {
            "paymentId": payment.id,
            "checkoutRequestId": payment.mpesa_checkout_request_id,
            "customerMessage": "Check your phone and enter your M-Pesa PIN to complete payment.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/payments/<id>/status — frontend polls this while waiting
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:payment_id>/status")
class PaymentStatus(MethodView):
    @jwt_required()
    @customer_only
    @blp.response(200, PaymentResponseSchema)
    def get(self, payment_id):
        customer_id = get_jwt_identity()
        payment = Payment.query.get(payment_id)
        if not payment or payment.order.customer_id != customer_id:
            abort(404, message="Payment not found")
        return payment.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/payments/mpesa/callback — Safaricom calls this, no auth
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/mpesa/callback")
class MpesaCallback(MethodView):
    @blp.response(200, MessageSchema)
    def post(self):
        from flask import request
        callback_body = request.get_json(silent=True) or {}

        parsed = parse_callback(callback_body)
        checkout_request_id = parsed["checkout_request_id"]

        payment = Payment.query.filter_by(
            mpesa_checkout_request_id=checkout_request_id
        ).first()

        if not payment:
            # Safaricom may retry callbacks for requests we don't recognise
            # (e.g. stale/test data) — always return 200 so they stop
            # retrying, but don't process anything.
            return {"message": "Callback received"}

        # Idempotency: if we've already processed this payment (e.g.
        # Safaricom sent a duplicate callback), don't process it twice
        if payment.status in ("completed", "failed"):
            return {"message": "Callback already processed"}

        payment.gateway_response = callback_body
        order = payment.order
        items = [{"product": item.product, "quantity": item.quantity} for item in order.items]

        if parsed["success"]:
            payment.status = "completed"
            payment.mpesa_receipt_number = parsed["mpesa_receipt_number"]
            payment.reference = parsed["mpesa_receipt_number"]
            payment.completed_at = datetime.now(timezone.utc)

            # Convert the stock reservation into an actual deduction —
            # the sale is now real, inventory is genuinely consumed.
            confirm_reservation(items)

            order.payment_reference = parsed["mpesa_receipt_number"]
            order.payment_confirmed_at = datetime.now(timezone.utc)
            order.status = "processing"  # payment confirmed -> order moves to processing

        else:
            payment.status = "failed"
            payment.failure_reason = parsed["result_desc"]

            # Payment failed/was cancelled by the customer — release the
            # reservation so the stock becomes available to others again.
            # Order stays "pending" so the customer can retry payment.
            release_reservation(items)

        db.session.commit()

        if parsed["success"]:
            # Payment confirmed — let the customer know their order is
            # now being prepared (status already moved to "processing" above)
            send_order_status_update_email(order)
            send_order_status_update_sms(order)

        return {"message": "Callback processed"}


# ─────────────────────────────────────────────────────────────────────────────
# Card payments (iPay/Pesapal) — Phase 3 continuation, not yet built
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/card/initiate")
class InitiateCardPayment(MethodView):
    @jwt_required()
    @customer_only
    @blp.response(501, MessageSchema)
    def post(self):
        abort(501, message="Card payment integration coming soon")


@blp.route("/card/callback")
class CardCallback(MethodView):
    @blp.response(200, MessageSchema)
    def post(self):
        # TODO: implement once iPay/Pesapal sandbox credentials are added
        return {"message": "Card payment integration coming soon"}