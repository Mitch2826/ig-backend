"""
app/services/sms_service.py
SMS notifications via Africa's Talking. Sandbox mode simulates sending
without actually delivering to real phones — same code path works for
production once AT_USERNAME/AT_API_KEY are swapped to live credentials.

Common in Kenyan e-commerce to pair SMS with email since not everyone
checks email regularly, but nearly everyone sees SMS immediately.
"""

import africastalking
from flask import current_app

_initialized = False


def _ensure_initialized():
    global _initialized
    if _initialized:
        return
    africastalking.initialize(
        current_app.config["AT_USERNAME"],
        current_app.config["AT_API_KEY"],
    )
    _initialized = True


def _normalize_phone(phone: str) -> str:
    """Africa's Talking expects +254712345678 format."""
    phone = phone.strip().replace(" ", "").replace("-", "")
    if phone.startswith("0"):
        phone = "+254" + phone[1:]
    elif phone.startswith("254"):
        phone = "+" + phone
    elif not phone.startswith("+"):
        phone = "+254" + phone
    return phone


def send_sms(phone: str, message: str) -> bool:
    """
    Returns True/False, never raises — an SMS failure should never break
    the calling flow (e.g. order placement succeeds even if the SMS fails).
    """
    try:
        _ensure_initialized()
        sms = africastalking.SMS
        response = sms.send(message, [_normalize_phone(phone)])
        recipients = response.get("SMSMessageData", {}).get("Recipients", [])
        return len(recipients) > 0 and recipients[0].get("status") == "Success"
    except Exception as e:
        current_app.logger.warning(f"Failed to send SMS to {phone}: {e}")
        return False


def send_order_confirmation_sms(order) -> bool:
    message = (
        f"I&G: Order {order.id} confirmed! Total KES {float(order.total):.0f}. "
        f"We'll notify you when it's on the way."
    )
    return send_sms(order.contact_phone, message)


def send_order_status_update_sms(order) -> bool:
    status_messages = {
        "out_for_delivery": f"I&G: Your order {order.id} is out for delivery!",
        "delivered": f"I&G: Your order {order.id} has been delivered. Thank you for shopping with us!",
        "cancelled": f"I&G: Your order {order.id} has been cancelled.",
    }
    message = status_messages.get(order.status)
    if not message:
        return False  # only SMS for the statuses customers most care about
    return send_sms(order.contact_phone, message)


def send_agent_assignment_sms(agent_phone: str, order_id: str) -> bool:
    message = f"I&G: New delivery assigned - Order {order_id}. Check your dashboard for details."
    return send_sms(agent_phone, message)