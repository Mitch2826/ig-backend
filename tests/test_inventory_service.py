"""
tests/test_inventory_service.py
Unit tests for app/services/inventory_service.py — the stock reservation
mechanism that prevents overselling. This is the single most important
piece of business logic to get right, since a bug here either lets two
customers buy the last unit (overselling) or permanently locks stock
that should be available (lost sales).
"""

import pytest
from app.services.inventory_service import (
    reserve_stock, release_reservation, confirm_reservation, InsufficientStockError,
)


def test_reserve_stock_reduces_available_stock(app, sample_product):
    """Reserving 5 units should reduce available_stock by exactly 5,
    without touching the actual physical stock count."""
    assert sample_product.available_stock == 20

    reserve_stock([{"product": sample_product, "quantity": 5}])

    assert sample_product.reserved_stock == 5
    assert sample_product.stock == 20  # unchanged
    assert sample_product.available_stock == 15


def test_reserve_stock_raises_when_insufficient(app, sample_product):
    """Trying to reserve more than available_stock should raise, not
    silently succeed or partially reserve."""
    with pytest.raises(InsufficientStockError) as exc_info:
        reserve_stock([{"product": sample_product, "quantity": 25}])

    assert exc_info.value.available == 20
    assert exc_info.value.requested == 25
    # Stock must remain untouched after a failed reservation attempt
    assert sample_product.reserved_stock == 0


def test_reserve_stock_exact_remaining_amount_succeeds(app, sample_product):
    """Reserving exactly the full available amount should succeed —
    boundary case, not an off-by-one error."""
    reserve_stock([{"product": sample_product, "quantity": 20}])
    assert sample_product.available_stock == 0


def test_two_sequential_reservations_cannot_oversell(app, sample_product):
    """Simulates two customers both trying to buy the last 15 units when
    only 20 are available. First succeeds, second should fail since only
    5 remain — this is the actual overselling prevention guarantee."""
    reserve_stock([{"product": sample_product, "quantity": 15}])
    assert sample_product.available_stock == 5

    with pytest.raises(InsufficientStockError):
        reserve_stock([{"product": sample_product, "quantity": 15}])

    # Second customer's failed attempt must not have reserved anything
    assert sample_product.reserved_stock == 15
    assert sample_product.available_stock == 5


def test_release_reservation_restores_available_stock(app, sample_product):
    """Cancelling an order (or a failed payment) should give the
    reserved units back without touching physical stock."""
    reserve_stock([{"product": sample_product, "quantity": 8}])
    assert sample_product.available_stock == 12

    release_reservation([{"product": sample_product, "quantity": 8}])

    assert sample_product.reserved_stock == 0
    assert sample_product.stock == 20
    assert sample_product.available_stock == 20


def test_release_reservation_never_goes_negative(app, sample_product):
    """Defensive test: releasing more than was ever reserved (shouldn't
    happen in normal flow, but the function should clamp at 0 rather
    than producing a negative reserved_stock, which would corrupt
    available_stock calculations)."""
    reserve_stock([{"product": sample_product, "quantity": 5}])
    release_reservation([{"product": sample_product, "quantity": 999}])

    assert sample_product.reserved_stock == 0  # clamped, not -994


def test_confirm_reservation_converts_to_real_deduction(app, sample_product):
    """When a payment succeeds, the reserved units should become an
    actual stock deduction — this is the moment inventory is genuinely
    consumed, not just held."""
    reserve_stock([{"product": sample_product, "quantity": 6}])
    assert sample_product.stock == 20
    assert sample_product.reserved_stock == 6

    confirm_reservation([{"product": sample_product, "quantity": 6}])

    assert sample_product.stock == 14  # actually deducted now
    assert sample_product.reserved_stock == 0
    assert sample_product.available_stock == 14


def test_confirm_reservation_never_goes_negative(app, sample_product):
    """Defensive test: confirming more than physical stock exists should
    clamp at 0 rather than going negative."""
    sample_product.stock = 3
    confirm_reservation([{"product": sample_product, "quantity": 10}])

    assert sample_product.stock == 0  # clamped, not -7


def test_multiple_items_reserved_in_single_call(app, sample_product, sample_category):
    """A real order has multiple line items — reserve_stock should handle
    a list of multiple products correctly, each independently."""
    from app.extensions import db
    from app.models import Product

    second_product = Product(
        name="Second Product", brand="Test Brand", description="Another test product",
        category_id=sample_category.id, subcategory_name="Test Subcategory",
        price=50.00, unit="per piece", sku="TEST-002", stock=10, low_stock_threshold=2,
    )
    db.session.add(second_product)
    db.session.commit()

    reserve_stock([
        {"product": sample_product, "quantity": 3},
        {"product": second_product, "quantity": 4},
    ])

    assert sample_product.available_stock == 17
    assert second_product.available_stock == 6


def test_partial_failure_in_multi_item_order_reserves_nothing(app, sample_product, sample_category):
    """If item 2 of a 2-item order can't be fully reserved, item 1 should
    NOT end up reserved either — reserve_stock() is now atomic: it
    validates every item's availability in a first pass before reserving
    anything in a second pass, so a failure partway through never leaves
    a half-reserved order. The caller no longer needs to rely on a
    database rollback to undo a partial reservation, because no partial
    reservation ever happens here in the first place."""
    from app.extensions import db
    from app.models import Product

    second_product = Product(
        name="Second Product", brand="Test Brand", description="Another test product",
        category_id=sample_category.id, subcategory_name="Test Subcategory",
        price=50.00, unit="per piece", sku="TEST-002", stock=2, low_stock_threshold=1,
    )
    db.session.add(second_product)
    db.session.commit()

    with pytest.raises(InsufficientStockError):
        reserve_stock([
            {"product": sample_product, "quantity": 3},   # would succeed alone
            {"product": second_product, "quantity": 10},  # fails — only 2 available
        ])

    # Neither product should show any reservation — true atomicity
    assert sample_product.reserved_stock == 0
    assert second_product.reserved_stock == 0


def test_duplicate_product_in_same_call_aggregates_quantity(app, sample_product):
    """Defensive case: if the same product appears twice in one order's
    items list (shouldn't happen from a normal cart, but guard against
    it), the two quantities should be combined and checked together
    against available_stock — not validated independently, which could
    let the combined total exceed what's actually available."""
    # sample_product has 20 available. Two lines of 12 each would
    # individually pass (12 <= 20) but together need 24, which should fail.
    with pytest.raises(InsufficientStockError) as exc_info:
        reserve_stock([
            {"product": sample_product, "quantity": 12},
            {"product": sample_product, "quantity": 12},
        ])

    assert exc_info.value.requested == 24  # the aggregated total, not 12
    assert sample_product.reserved_stock == 0  # nothing reserved on failure