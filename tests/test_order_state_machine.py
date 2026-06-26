"""
tests/test_order_state_machine.py
Tests for the order status state machine (VALID_TRANSITIONS in
app/models/order.py). Getting this wrong could let an order skip steps
(e.g. pending -> delivered with no payment confirmation) or get stuck
unable to progress.
"""

from datetime import datetime, timezone
from app.extensions import db
from app.models import Order, VALID_TRANSITIONS


def _make_order(customer_id, status="pending"):
    order = Order(
        customer_id=customer_id, subtotal=100, delivery_fee=0, total=100,
        status=status, fulfilment_type="pickup",
        contact_first_name="Test", contact_last_name="Customer",
        contact_phone="+254700000000", contact_email="test@test.com",
        payment_method="mpesa",
    )
    db.session.add(order)
    db.session.commit()
    return order


# ─────────────────────────────────────────────────────────────────────────────
# Valid transitions — each should be allowed
# ─────────────────────────────────────────────────────────────────────────────
def test_pending_can_transition_to_processing(app, customer_user):
    order = _make_order(customer_user.id, status="pending")
    assert order.can_transition_to("processing") is True


def test_pending_can_transition_to_cancelled(app, customer_user):
    order = _make_order(customer_user.id, status="pending")
    assert order.can_transition_to("cancelled") is True


def test_processing_can_transition_to_out_for_delivery(app, customer_user):
    order = _make_order(customer_user.id, status="processing")
    assert order.can_transition_to("out_for_delivery") is True


def test_processing_can_transition_to_cancelled(app, customer_user):
    order = _make_order(customer_user.id, status="processing")
    assert order.can_transition_to("cancelled") is True


def test_out_for_delivery_can_transition_to_delivered(app, customer_user):
    order = _make_order(customer_user.id, status="out_for_delivery")
    assert order.can_transition_to("delivered") is True


def test_cancellation_requested_can_transition_to_cancelled(app, customer_user):
    """Admin approves the customer's cancellation request."""
    order = _make_order(customer_user.id, status="cancellation_requested")
    assert order.can_transition_to("cancelled") is True


def test_cancellation_requested_can_transition_to_processing(app, customer_user):
    """Admin declines the customer's cancellation request — order resumes."""
    order = _make_order(customer_user.id, status="cancellation_requested")
    assert order.can_transition_to("processing") is True


# ─────────────────────────────────────────────────────────────────────────────
# Invalid transitions — each should be blocked
# ─────────────────────────────────────────────────────────────────────────────
def test_pending_cannot_skip_to_delivered(app, customer_user):
    """The most important invalid case: an order must never go straight
    from pending to delivered without passing through processing and
    out_for_delivery — this would mean no payment confirmation step
    ever happened."""
    order = _make_order(customer_user.id, status="pending")
    assert order.can_transition_to("delivered") is False


def test_pending_cannot_skip_to_out_for_delivery(app, customer_user):
    order = _make_order(customer_user.id, status="pending")
    assert order.can_transition_to("out_for_delivery") is False


def test_processing_cannot_skip_to_delivered(app, customer_user):
    """Must pass through out_for_delivery first."""
    order = _make_order(customer_user.id, status="processing")
    assert order.can_transition_to("delivered") is False


def test_delivered_is_terminal(app, customer_user):
    """A delivered order can never transition to anything else —
    no take-backs once it's marked delivered."""
    order = _make_order(customer_user.id, status="delivered")
    assert order.can_transition_to("processing") is False
    assert order.can_transition_to("cancelled") is False
    assert order.can_transition_to("out_for_delivery") is False


def test_cancelled_is_terminal(app, customer_user):
    """A cancelled order can never be resurrected."""
    order = _make_order(customer_user.id, status="cancelled")
    assert order.can_transition_to("pending") is False
    assert order.can_transition_to("processing") is False
    assert order.can_transition_to("delivered") is False


def test_out_for_delivery_cannot_go_back_to_processing(app, customer_user):
    """No going backwards in the pipeline."""
    order = _make_order(customer_user.id, status="out_for_delivery")
    assert order.can_transition_to("processing") is False


def test_cancellation_requested_cannot_skip_to_delivered(app, customer_user):
    """A cancellation request must be resolved (approved->cancelled or
    declined->processing) — it can't be bypassed straight to delivered."""
    order = _make_order(customer_user.id, status="cancellation_requested")
    assert order.can_transition_to("delivered") is False
    assert order.can_transition_to("out_for_delivery") is False


def test_unknown_status_has_no_valid_transitions(app, customer_user):
    """Defensive: an order somehow in an unrecognised status (shouldn't
    happen, but if it did due to a data issue) should not be able to
    transition anywhere, rather than crashing or defaulting to allowing
    everything."""
    order = _make_order(customer_user.id, status="some_unexpected_status")
    assert order.can_transition_to("processing") is False
    assert order.can_transition_to("delivered") is False


# ─────────────────────────────────────────────────────────────────────────────
# Completeness check — every status defined in VALID_TRANSITIONS should
# be exercised above. This test fails loudly if someone adds a new status
# to the model without anyone writing tests for its transitions.
# ─────────────────────────────────────────────────────────────────────────────
def test_all_defined_statuses_have_transition_tests():
    """Not a behavioral test — a safeguard that the test suite itself
    stays in sync with the model. If a new status is added to
    VALID_TRANSITIONS in app/models/order.py, this test will fail until
    someone adds corresponding tests above, rather than silently leaving
    a new status untested."""
    expected_statuses = {
        "pending", "processing", "out_for_delivery",
        "delivered", "cancelled", "cancellation_requested",
    }
    assert set(VALID_TRANSITIONS.keys()) == expected_statuses, (
        "VALID_TRANSITIONS has changed — update this test file to cover "
        "the new/changed status before considering this task done."
    )