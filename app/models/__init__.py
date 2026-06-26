"""
app/models/__init__.py
Imports every model so:
1. Alembic (flask db migrate) can discover all tables when generating migrations
2. Other parts of the app can do `from app.models import User, Product, ...`
   instead of reaching into individual files

IMPORTANT: whenever a new model file is added, it must be imported here too,
or Alembic will silently not know it exists and won't generate a migration
for it.
"""

from app.models.user import User
from app.models.category import Category, Subcategory
from app.models.product import Product, ProductImage
from app.models.order import Order, OrderItem, ORDER_STATUSES, VALID_TRANSITIONS
from app.models.delivery_agent import DeliveryAgent
from app.models.return_cancellation import CancellationRequest, ReturnRequest, RETURN_REASONS
from app.models.payment import Payment
from app.models.settings import Setting, HeroSlide, AuditLog

__all__ = [
    "User",
    "Category", "Subcategory",
    "Product", "ProductImage",
    "Order", "OrderItem", "ORDER_STATUSES", "VALID_TRANSITIONS",
    "DeliveryAgent",
    "CancellationRequest", "ReturnRequest", "RETURN_REASONS",
    "Payment",
    "Setting", "HeroSlide", "AuditLog",
]