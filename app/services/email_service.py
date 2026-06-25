"""
app/services/email_service.py
Transactional email sending via Flask-Mail. Uses Mailtrap in development
(emails land in a test inbox, never actually delivered) and should be
pointed at AWS SES in production by swapping the MAIL_* env vars — no
code changes needed, same send_email() function either way.

Each specific email type (order confirmation, password reset, etc.) has
its own function that builds the appropriate subject/body and calls
send_email() — keeps the actual SMTP mechanics in one place.
"""

from flask import current_app
from flask_mail import Message
from app.extensions import mail


def send_email(to: str, subject: str, body: str, html: str = None) -> bool:
    """
    Core send function. Returns True/False rather than raising, so a
    failed email never breaks the calling code's main flow (e.g. an order
    should still succeed even if the confirmation email fails to send).
    """
    try:
        msg = Message(
            subject=subject,
            recipients=[to],
            body=body,
            html=html,
            sender=current_app.config["MAIL_DEFAULT_SENDER"],
        )
        mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.warning(f"Failed to send email to {to}: {e}")
        return False


def send_order_confirmation_email(order) -> bool:
    """order: an Order model instance."""
    items_lines = "\n".join(
        f"  - {item.product.name if item.product else 'Item'} x{item.quantity} - "
        f"KES {float(item.price) * item.quantity:.2f}"
        for item in order.items
    )

    body = f"""Hi {order.contact_first_name},

Thank you for your order! Here's a summary:

Order ID: {order.id}
{items_lines}

Subtotal: KES {float(order.subtotal):.2f}
Delivery Fee: KES {float(order.delivery_fee):.2f}
Total: KES {float(order.total):.2f}

Payment Method: {order.payment_method}
Fulfilment: {order.fulfilment_type}

We'll notify you as your order progresses.

Thank you for shopping with I&G.
"""
    return send_email(order.contact_email, f"Order Confirmation - {order.id}", body)


def send_order_status_update_email(order) -> bool:
    """Sent whenever admin/agent advances an order's status."""
    status_messages = {
        "processing": "Your order is now being prepared.",
        "out_for_delivery": "Your order is on its way!",
        "delivered": "Your order has been delivered. Enjoy!",
        "cancelled": "Your order has been cancelled.",
    }
    message = status_messages.get(order.status, f"Your order status is now: {order.status}")

    body = f"""Hi {order.contact_first_name},

Update on your order {order.id}:

{message}

Thank you for shopping with I&G.
"""
    return send_email(order.contact_email, f"Order Update - {order.id}", body)


def send_password_reset_email(email: str, reset_link: str) -> bool:
    body = f"""Hi,

We received a request to reset your password. Click the link below to set a new password:

{reset_link}

This link expires in 1 hour. If you didn't request this, you can safely ignore this email.

I&G Support
"""
    return send_email(email, "Reset Your Password - I&G", body)


def send_agent_welcome_email(email: str, name: str, temporary_password: str) -> bool:
    """Sent when admin creates a new delivery agent account."""
    body = f"""Hi {name},

You've been added as a delivery agent on the I&G platform. Here are your login details:

Email: {email}
Temporary Password: {temporary_password}

Please log in and change your password as soon as possible.

I&G Operations Team
"""
    return send_email(email, "Welcome to I&G - Delivery Agent Account Created", body)


def send_return_request_resolution_email(order, return_request) -> bool:
    """Sent when admin approves or declines a return request."""
    if return_request.status == "approved":
        message = (
            "Your return request has been approved. A refund will be processed to your "
            "original payment method within 5-7 business days."
        )
    else:
        message = (
            "After review, we were unable to approve your return request for this order. "
            "Please contact support if you have questions."
        )

    body = f"""Hi {order.contact_first_name},

Update on your return request for order {order.id}:

{message}

I&G Support
"""
    return send_email(order.contact_email, f"Return Request Update - {order.id}", body)