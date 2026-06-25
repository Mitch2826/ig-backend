"""
app/utils/decorators.py
Role-based access decorators for routes. These read the role embedded in
the JWT (set at login time) and reject the request with 403 if the
logged-in user doesn't have permission.

Usage — always stack with @jwt_required() first:
    @jwt_required()
    @admin_only
    def delete(self, product_id):
        ...

Mirrors the role logic in the frontend's ProtectedRoute.tsx and
AuthContext.tsx (isAdmin, isStoreManager, isDeliveryAgent, isCustomer).
"""

from functools import wraps
from flask_jwt_extended import get_jwt
from flask_smorest import abort


def _get_role_from_token() -> str:
    claims = get_jwt()
    return claims.get("role", "")


def admin_only(fn):
    """Restricts to role == 'admin'. Used for: deleting products, viewing
    customers list, reports, settings — matches frontend's admin-only
    routes in ProtectedRoute.tsx."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _get_role_from_token() != "admin":
            abort(403, message="This action requires admin privileges")
        return fn(*args, **kwargs)
    return wrapper


def staff_only(fn):
    """Restricts to role in ('admin', 'store_manager'). Used for: most
    admin panel routes (products, categories, orders, inventory) that
    both roles can access — matches frontend's isBackendUser check
    for admin/store_manager (excluding delivery_agent, which has its
    own separate dashboard and decorator below)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _get_role_from_token() not in ("admin", "store_manager"):
            abort(403, message="This action requires admin or store manager privileges")
        return fn(*args, **kwargs)
    return wrapper


def delivery_agent_only(fn):
    """Restricts to role == 'delivery_agent'. Used for: the agent's own
    dashboard endpoints (/api/delivery/my-orders etc.) — an agent should
    only ever see their own assigned deliveries, never anyone else's."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _get_role_from_token() != "delivery_agent":
            abort(403, message="This action requires delivery agent privileges")
        return fn(*args, **kwargs)
    return wrapper


def customer_only(fn):
    """Restricts to role == 'customer'. Used for: checkout, placing orders,
    customer-side order history — matches frontend's customer-only
    protected routes (e.g. /checkout, /orders)."""
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if _get_role_from_token() != "customer":
            abort(403, message="This action is only available to customers")
        return fn(*args, **kwargs)
    return wrapper