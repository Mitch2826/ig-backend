"""
app/jobs/scheduled_jobs.py
Background jobs run in-process via APScheduler (no separate worker
process needed at our current scale — see config decision in our
build plan to use APScheduler over Celery until traffic justifies it).

Jobs:
1. check_low_stock — runs every hour, emails admin a summary of products
   at or below their low_stock_threshold.
2. cleanup_abandoned_payments — runs every 15 minutes, finds orders stuck
   at 'pending' with a payment that's been pending for >30 minutes
   (customer started checkout but never completed/the callback never
   arrived), releases their stock reservation so it doesn't stay locked
   forever, and marks the payment as 'timeout'.

Jobs are registered onto the scheduler in app/__init__.py's create_app(),
not here — this file only defines the job functions themselves.
"""

from datetime import datetime, timedelta, timezone

from app.extensions import db
from app.models import Product, Payment
from app.services.email_service import send_email
from app.services.inventory_service import release_reservation


def check_low_stock(app):
    """
    app: the Flask app instance, passed in because APScheduler jobs run
    outside the normal request context — we need to push an app context
    manually to use db/current_app inside this function.
    """
    with app.app_context():
        low_stock_products = [
            p for p in Product.query.filter_by(is_active=True).all()
            if p.available_stock <= p.low_stock_threshold
        ]

        if not low_stock_products:
            return

        lines = "\n".join(
            f"  - {p.name} (SKU: {p.sku}): {p.available_stock} left "
            f"(threshold: {p.low_stock_threshold})"
            for p in low_stock_products
        )

        body = f"""Low stock alert — {len(low_stock_products)} product(s) need attention:

{lines}

Log in to the admin dashboard to restock.
"""
        admin_email = app.config.get("MAIL_DEFAULT_SENDER")  # TODO: replace with actual admin notification email/list once that's configurable in Settings
        send_email(admin_email, f"Low Stock Alert - {len(low_stock_products)} products", body)
        app.logger.info(f"Low stock check: {len(low_stock_products)} products flagged")


def cleanup_abandoned_payments(app):
    """
    Finds payments stuck at 'pending' for more than 30 minutes — these are
    almost always cases where the customer abandoned the STK Push prompt
    (didn't enter their PIN) and Safaricom's callback either never fired
    or got lost. Without this job, that order's reserved stock would stay
    locked forever, permanently reducing available_stock for no reason.
    """
    with app.app_context():
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)

        stale_payments = Payment.query.filter(
            Payment.status == "pending",
            Payment.initiated_at < cutoff,
        ).all()

        for payment in stale_payments:
            order = payment.order
            if not order or order.status != "pending":
                # Order may have already been resolved another way
                # (e.g. customer cancelled, or a later payment succeeded)
                continue

            items = [{"product": item.product, "quantity": item.quantity} for item in order.items]
            release_reservation(items)

            payment.status = "timeout"
            payment.failure_reason = "Payment timed out — no confirmation received within 30 minutes"

        if stale_payments:
            db.session.commit()
            app.logger.info(f"Cleaned up {len(stale_payments)} abandoned payment(s)")