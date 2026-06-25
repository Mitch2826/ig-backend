"""
app/services/inventory_service.py
Stock reservation logic — the mechanism that prevents two customers from
both successfully buying the last unit of a product at the same time.

How it works:
1. When an order is placed, we reserve the requested quantity for each
   item (Product.reserved_stock += quantity). This happens in the SAME
   database transaction as creating the order, so it's atomic.
2. available_stock (= stock - reserved_stock) immediately reflects this,
   so other customers browsing the storefront see accurate availability.
3. If payment succeeds: reserved units convert to a real deduction
   (stock -= quantity, reserved_stock -= quantity) — see confirm_reservation().
4. If payment fails/times out/order is cancelled: the reservation is
   released (reserved_stock -= quantity) without touching `stock` — see
   release_reservation().

This module raises InsufficientStockError rather than silently failing,
so the Orders route can return a clear 400 to the customer ("Sorry, only
3 left") instead of creating an order that can never be fulfilled.
"""

from typing import List, Dict, Any
from app.extensions import db
from app.models import Product


class InsufficientStockError(Exception):
    def __init__(self, product_name: str, available: int, requested: int):
        self.product_name = product_name
        self.available = available
        self.requested = requested
        super().__init__(
            f"Insufficient stock for '{product_name}': "
            f"requested {requested}, only {available} available"
        )


def reserve_stock(items: List[Dict[str, Any]]) -> None:
    """
    items: [{"product": Product, "quantity": int}, ...]
    Raises InsufficientStockError if any item can't be fully reserved.
    Caller is responsible for committing the transaction afterward —
    this function only stages the changes via db.session, it doesn't commit,
    so it can be part of a larger atomic order-creation transaction.
    """
    for item in items:
        product: Product = item["product"]
        quantity: int = item["quantity"]

        if product.available_stock < quantity:
            raise InsufficientStockError(product.name, product.available_stock, quantity)

        product.reserved_stock += quantity


def release_reservation(items: List[Dict[str, Any]]) -> None:
    """
    Called when an order is cancelled or a payment fails/times out —
    gives the reserved units back to the available pool without touching
    the actual physical stock count (since nothing was ever fulfilled).
    """
    for item in items:
        product: Product = item["product"]
        quantity: int = item["quantity"]
        product.reserved_stock = max(0, product.reserved_stock - quantity)


def confirm_reservation(items: List[Dict[str, Any]]) -> None:
    """
    Called when a payment is confirmed successful — converts the
    reservation into an actual stock deduction. This is the point where
    inventory is genuinely consumed.
    """
    for item in items:
        product: Product = item["product"]
        quantity: int = item["quantity"]
        product.stock = max(0, product.stock - quantity)
        product.reserved_stock = max(0, product.reserved_stock - quantity)