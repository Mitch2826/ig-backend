"""
app/blueprints/admin/routes.py
Admin/store_manager operations: dashboard metrics, inventory management,
settings, customers, reports.

PUBLIC (no auth):
GET    /api/admin/settings/public           feature flags + safe store fields
                                              (storefront uses this to decide
                                              whether to render e.g. Flash Deals)

GET    /api/admin/dashboard               metrics, recent orders, top products, low stock
GET    /api/admin/inventory                full product list with stock status
PATCH  /api/admin/inventory/<id>            update single product's stock
PATCH  /api/admin/inventory/bulk            bulk update stock for multiple products

GET    /api/admin/settings                  feature flags + store settings + hero slides
PATCH  /api/admin/settings/features          update feature flags (admin only)
PATCH  /api/admin/settings/store             update store settings (admin only)
GET    /api/admin/settings/hero              list hero slides
POST   /api/admin/settings/hero               create hero slide (admin only)
PATCH  /api/admin/settings/hero/<id>          update hero slide (admin only)
DELETE /api/admin/settings/hero/<id>          delete hero slide (admin only)

GET    /api/admin/customers                  list customers with tier (admin only)
GET    /api/admin/customers/<id>              single customer detail (admin only)

GET    /api/admin/reports                    revenue/orders/payment breakdown (admin only)
"""

from datetime import datetime, timedelta, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, or_

from app.extensions import db
from app.models import Product, Order, OrderItem, User, HeroSlide, AuditLog
from app.utils.decorators import staff_only, admin_only
from app.services.settings_service import get_all_settings, set_setting, get_setting
from app.blueprints.admin.schemas import (
    DashboardResponseSchema, InventoryUpdateSchema, BulkInventoryUpdateSchema,
    FeatureFlagsSchema, StoreSettingsSchema, HeroSlideSchema,
    CustomerListQuerySchema, CustomerListResponseSchema,
    ReportsQuerySchema, ReportsResponseSchema, MessageSchema,
)
from app.blueprints.products.schemas import ProductResponseSchema, ProductListResponseSchema

blp = Blueprint("admin", __name__, url_prefix="/api/admin", description="Admin operations")


def _log(user_id, action, resource_type, resource_id=None, details=None):
    db.session.add(AuditLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=resource_id, details=details,
    ))


def _stock_status(product: Product) -> str:
    if product.available_stock == 0:
        return "out_of_stock"
    if product.available_stock <= product.low_stock_threshold:
        return "low_stock"
    return "in_stock"


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/admin/settings/public — PUBLIC, no auth required
# Exposes only the feature flags + a few harmless display fields the
# storefront needs (e.g. to decide whether to render the Flash Deals
# section, or show "Free delivery over KES X" messaging). Deliberately
# does NOT expose anything sensitive (mpesa paybill, support email, etc.)
# — that full set stays staff-only via the existing SettingsGet route below.
#
# IMPORTANT: route ordering — flask-smorest/Flask matches the most
# specific literal path before falling through to a parameterized one,
# but since "/settings/public" and "/settings/hero" are both literal
# children of "/settings", and neither is a prefix of the other, there's
# no ambiguity here regardless of declaration order.
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/settings/public")
class PublicSettings(MethodView):
    def get(self):
        settings = get_all_settings()
        return {
            "features": {
                "salesAndDiscounts": settings["feature.sales_and_discounts"] == "true",
                "flashDealsSection": settings["feature.flash_deals_section"] == "true",
                "freeDelivery": settings["feature.free_delivery"] == "true",
                "googleAuth": settings["feature.google_auth"] == "true",
                "dynamicHero": settings["feature.dynamic_hero"] == "true",
            },
            "store": {
                "deliveryFee": float(settings["store.delivery_fee"]),
                "minOrderAmount": float(settings["store.min_order_amount"]),
                "freeDeliveryThreshold": float(settings["store.free_delivery_threshold"]),
                "storeName": settings["store.name"],
                "storeAddress": settings["store.address"],
                "storeHours": settings["store.hours"],
            },
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/admin/dashboard
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/dashboard")
class Dashboard(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, DashboardResponseSchema)
    def get(self):
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        orders_today = Order.query.filter(
            Order.created_at >= today_start, Order.status != "cancelled"
        ).all()

        revenue_today = sum(float(o.total) for o in orders_today)

        total_customers = User.query.filter_by(role="customer").count()

        low_stock_products = [
            p for p in Product.query.filter_by(is_active=True).all()
            if _stock_status(p) in ("low_stock", "out_of_stock")
        ]

        recent_orders = (
            Order.query.order_by(Order.created_at.desc()).limit(5).all()
        )

        top_products_query = (
            db.session.query(
                Product.id, Product.name, Product.stock, Product.reserved_stock,
                func.sum(OrderItem.quantity).label("units_sold"),
                func.sum(OrderItem.quantity * OrderItem.price).label("revenue"),
            )
            .join(OrderItem, OrderItem.product_id == Product.id)
            .join(Order, Order.id == OrderItem.order_id)
            .filter(Order.status.in_(["delivered", "out_for_delivery", "processing"]))
            .group_by(Product.id)
            .order_by(func.sum(OrderItem.quantity).desc())
            .limit(5)
            .all()
        )

        return {
            "metrics": {
                "revenueToday": revenue_today,
                "ordersToday": len(orders_today),
                "totalCustomers": total_customers,
                "lowStockCount": len(low_stock_products),
            },
            "recentOrders": [
                {
                    "id": o.id,
                    "customer": f"{o.contact_first_name} {o.contact_last_name}",
                    "amount": float(o.total),
                    "status": o.status,
                    "itemsCount": sum(i.quantity for i in o.items),
                    "paymentMethod": o.payment_method,
                    "createdAt": o.created_at.isoformat() if o.created_at else None,
                }
                for o in recent_orders
            ],
            "topProducts": [
                {
                    "id": row.id, "name": row.name, "category": None,
                    "unitsSold": int(row.units_sold), "revenue": float(row.revenue),
                    "stock": max(0, row.stock - row.reserved_stock),
                }
                for row in top_products_query
            ],
            "lowStockItems": [
                {
                    "id": p.id, "name": p.name, "sku": p.sku,
                    "stock": p.available_stock, "threshold": p.low_stock_threshold,
                }
                for p in low_stock_products[:10]
            ],
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/admin/inventory
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/inventory")
class InventoryList(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, ProductListResponseSchema)
    def get(self):
        products = Product.query.order_by(Product.name).all()
        return {
            "items": [p.to_dict(apply_sale_price=True) for p in products],
            "total": len(products), "page": 1, "perPage": len(products) or 1,
            "totalPages": 1,
        }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/admin/inventory/<id> — update single product's stock
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/inventory/<string:product_id>")
class InventoryUpdate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(InventoryUpdateSchema)
    @blp.response(200, ProductResponseSchema)
    def patch(self, data, product_id):
        product = Product.query.get(product_id)
        if not product:
            abort(404, message="Product not found")

        changes = {}
        if "stock" in data and data["stock"] != product.stock:
            changes["stock"] = {"from": product.stock, "to": data["stock"]}
            product.stock = data["stock"]
        if "lowStockThreshold" in data:
            product.low_stock_threshold = data["lowStockThreshold"]

        if changes:
            _log(get_jwt_identity(), "inventory.updated", "product", product.id, changes)

        db.session.commit()
        return product.to_dict(apply_sale_price=True)


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/admin/inventory/bulk
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/inventory/bulk")
class InventoryBulkUpdate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(BulkInventoryUpdateSchema)
    @blp.response(200, MessageSchema)
    def patch(self, data):
        products = Product.query.filter(Product.id.in_(data["productIds"])).all()
        if len(products) != len(data["productIds"]):
            abort(400, message="One or more product IDs were not found")

        for product in products:
            product.stock = data["stock"]

        _log(get_jwt_identity(), "inventory.bulk_updated", "product", None,
             {"productIds": data["productIds"], "newStock": data["stock"]})
        db.session.commit()

        return {"message": f"Updated stock for {len(products)} products"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/admin/settings — feature flags + store settings + hero slides
# (full set, staff only — see PublicSettings above for the public subset)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/settings")
class SettingsGet(MethodView):
    @jwt_required()
    @staff_only
    def get(self):
        settings = get_all_settings()
        slides = HeroSlide.query.order_by(HeroSlide.display_order).all()

        return {
            "features": {
                "salesAndDiscounts": settings["feature.sales_and_discounts"] == "true",
                "flashDealsSection": settings["feature.flash_deals_section"] == "true",
                "freeDelivery": settings["feature.free_delivery"] == "true",
                "googleAuth": settings["feature.google_auth"] == "true",
                "dynamicHero": settings["feature.dynamic_hero"] == "true",
            },
            "store": {
                "storeName": settings["store.name"],
                "storeAddress": settings["store.address"],
                "storeHours": settings["store.hours"],
                "storePhone": settings["store.phone"],
                "supportEmail": settings["store.support_email"],
                "deliveryFee": float(settings["store.delivery_fee"]),
                "minOrderAmount": float(settings["store.min_order_amount"]),
                "mpesaPaybill": settings["store.mpesa_paybill"],
                "mpesaAccountPrefix": settings["store.mpesa_account_prefix"],
                "freeDeliveryThreshold": float(settings["store.free_delivery_threshold"]),
            },
            "heroSlides": [s.to_dict() for s in slides],
        }


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/admin/settings/features — admin only
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/settings/features")
class SettingsFeaturesUpdate(MethodView):
    @jwt_required()
    @admin_only
    @blp.arguments(FeatureFlagsSchema)
    @blp.response(200, MessageSchema)
    def patch(self, data):
        key_map = {
            "salesAndDiscounts": "feature.sales_and_discounts",
            "flashDealsSection": "feature.flash_deals_section",
            "freeDelivery": "feature.free_delivery",
            "googleAuth": "feature.google_auth",
            "dynamicHero": "feature.dynamic_hero",
        }
        for input_key, setting_key in key_map.items():
            if input_key in data:
                set_setting(setting_key, "true" if data[input_key] else "false")

        _log(get_jwt_identity(), "settings.features_updated", "settings", None, data)
        db.session.commit()
        return {"message": "Feature flags updated"}


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/admin/settings/store — admin only
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/settings/store")
class SettingsStoreUpdate(MethodView):
    @jwt_required()
    @admin_only
    @blp.arguments(StoreSettingsSchema)
    @blp.response(200, MessageSchema)
    def patch(self, data):
        key_map = {
            "storeName": "store.name", "storeAddress": "store.address",
            "storeHours": "store.hours", "storePhone": "store.phone",
            "supportEmail": "store.support_email", "deliveryFee": "store.delivery_fee",
            "minOrderAmount": "store.min_order_amount", "mpesaPaybill": "store.mpesa_paybill",
            "mpesaAccountPrefix": "store.mpesa_account_prefix",
            "freeDeliveryThreshold": "store.free_delivery_threshold",
        }
        for input_key, setting_key in key_map.items():
            if input_key in data:
                set_setting(setting_key, str(data[input_key]))

        _log(get_jwt_identity(), "settings.store_updated", "settings", None, data)
        db.session.commit()
        return {"message": "Store settings updated"}


# ─────────────────────────────────────────────────────────────────────────────
# Hero slides — list / create / update / delete
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/settings/hero")
class HeroSlideList(MethodView):
    @jwt_required()
    @staff_only
    def get(self):
        slides = HeroSlide.query.order_by(HeroSlide.display_order).all()
        return [s.to_dict() for s in slides]

    @jwt_required()
    @admin_only
    @blp.arguments(HeroSlideSchema)
    def post(self, data):
        count = HeroSlide.query.count()
        if count >= 5:
            abort(400, message="Maximum of 5 hero slides allowed")

        slide = HeroSlide(
            title=data["title"], subtitle=data.get("subtitle"), badge=data.get("badge"),
            cta=data.get("cta", "Shop Now"), cta_link=data.get("ctaLink", "/"),
            image_url=data.get("image"), bg_gradient_from=data.get("bgFrom", "#1A5C38"),
            bg_gradient_to=data.get("bgTo", "#0f3b22"), is_active=data.get("isActive", True),
            display_order=count,
        )
        db.session.add(slide)
        _log(get_jwt_identity(), "hero_slide.created", "hero_slide", None, {"title": slide.title})
        db.session.commit()
        return slide.to_dict()


@blp.route("/settings/hero/<string:slide_id>")
class HeroSlideUpdate(MethodView):
    @jwt_required()
    @admin_only
    @blp.arguments(HeroSlideSchema)
    def patch(self, data, slide_id):
        slide = HeroSlide.query.get(slide_id)
        if not slide:
            abort(404, message="Hero slide not found")

        field_map = {
            "title": "title", "subtitle": "subtitle", "badge": "badge",
            "cta": "cta", "ctaLink": "cta_link", "image": "image_url",
            "bgFrom": "bg_gradient_from", "bgTo": "bg_gradient_to", "isActive": "is_active",
        }
        for input_key, model_attr in field_map.items():
            if input_key in data:
                setattr(slide, model_attr, data[input_key])

        _log(get_jwt_identity(), "hero_slide.updated", "hero_slide", slide.id, data)
        db.session.commit()
        return slide.to_dict()

    @jwt_required()
    @admin_only
    @blp.response(200, MessageSchema)
    def delete(self, slide_id):
        slide = HeroSlide.query.get(slide_id)
        if not slide:
            abort(404, message="Hero slide not found")

        if HeroSlide.query.count() <= 1:
            abort(400, message="At least one hero slide must remain")

        _log(get_jwt_identity(), "hero_slide.deleted", "hero_slide", slide.id, {"title": slide.title})
        db.session.delete(slide)
        db.session.commit()
        return {"message": "Hero slide deleted"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/admin/customers — admin only
# ─────────────────────────────────────────────────────────────────────────────
def _customer_tier(total_spent: float, total_orders: int) -> str:
    if total_orders <= 1:
        return "new"
    if total_spent >= 30000:
        return "vip"
    return "regular"


@blp.route("/customers")
class CustomerList(MethodView):
    @jwt_required()
    @admin_only
    @blp.arguments(CustomerListQuerySchema, location="query")
    @blp.response(200, CustomerListResponseSchema)
    def get(self, args):
        query = User.query.filter_by(role="customer")

        if args["search"]:
            term = f"%{args['search']}%"
            query = query.filter(
                or_(User.first_name.ilike(term), User.last_name.ilike(term),
                    User.email.ilike(term), User.phone.ilike(term))
            )

        customers = query.all()

        enriched = []
        for customer in customers:
            orders = [o for o in customer.orders if o.status != "cancelled"]
            total_spent = sum(float(o.total) for o in orders)
            last_order = max(orders, key=lambda o: o.created_at) if orders else None
            tier = _customer_tier(total_spent, len(orders))

            if args["tier"] != "all" and tier != args["tier"]:
                continue

            enriched.append({
                "id": customer.id, "firstName": customer.first_name, "lastName": customer.last_name,
                "email": customer.email, "phone": customer.phone,
                "joinedAt": customer.created_at.isoformat() if customer.created_at else None,
                "totalOrders": len(orders), "totalSpent": total_spent,
                "lastOrderAt": last_order.created_at.isoformat() if last_order else None,
                "tier": tier,
            })

        enriched.sort(key=lambda c: c["totalSpent"], reverse=True)

        total = len(enriched)
        start = (args["page"] - 1) * args["perPage"]
        page_items = enriched[start:start + args["perPage"]]

        return {
            "items": page_items, "total": total, "page": args["page"], "perPage": args["perPage"],
            "totalPages": max(1, (total + args["perPage"] - 1) // args["perPage"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/admin/reports — admin only
# ─────────────────────────────────────────────────────────────────────────────
RANGE_DAYS = {"today": 1, "7d": 7, "30d": 30, "90d": 90}


@blp.route("/reports")
class Reports(MethodView):
    @jwt_required()
    @admin_only
    @blp.arguments(ReportsQuerySchema, location="query")
    @blp.response(200, ReportsResponseSchema)
    def get(self, args):
        days = RANGE_DAYS[args["range"]]
        start_date = datetime.now(timezone.utc) - timedelta(days=days)

        orders = Order.query.filter(
            Order.created_at >= start_date, Order.status != "cancelled"
        ).all()

        total_revenue = sum(float(o.total) for o in orders)
        total_orders = len(orders)
        avg_order_value = total_revenue / total_orders if total_orders else 0

        mpesa_revenue = sum(float(o.total) for o in orders if o.payment_method == "mpesa")
        card_revenue = sum(float(o.total) for o in orders if o.payment_method == "debit_card")

        delivery_count = sum(1 for o in orders if o.fulfilment_type == "delivery")
        pickup_count = sum(1 for o in orders if o.fulfilment_type == "pickup")

        daily = {}
        for o in orders:
            day_key = o.created_at.date().isoformat()
            if day_key not in daily:
                daily[day_key] = {"revenue": 0, "orders": 0}
            daily[day_key]["revenue"] += float(o.total)
            daily[day_key]["orders"] += 1

        daily_revenue = [
            {"date": k, "revenue": v["revenue"], "orders": v["orders"]}
            for k, v in sorted(daily.items())
        ]

        category_revenue = {}
        for o in orders:
            for item in o.items:
                if item.product and item.product.category:
                    cat_name = item.product.category.name
                    category_revenue[cat_name] = category_revenue.get(cat_name, 0) + float(item.price) * item.quantity

        category_breakdown = [
            {
                "category": cat, "revenue": rev,
                "percentage": round((rev / total_revenue * 100) if total_revenue else 0, 1),
            }
            for cat, rev in sorted(category_revenue.items(), key=lambda x: x[1], reverse=True)
        ]

        product_sales = {}
        for o in orders:
            for item in o.items:
                if not item.product:
                    continue
                pid = item.product.id
                if pid not in product_sales:
                    product_sales[pid] = {
                        "id": pid, "name": item.product.name, "category": None,
                        "unitsSold": 0, "revenue": 0.0, "stock": item.product.available_stock,
                    }
                product_sales[pid]["unitsSold"] += item.quantity
                product_sales[pid]["revenue"] += float(item.price) * item.quantity

        top_products = sorted(
            product_sales.values(), key=lambda p: p["unitsSold"], reverse=True
        )[:10]

        return {
            "totalRevenue": total_revenue, "totalOrders": total_orders,
            "avgOrderValue": avg_order_value, "dailyRevenue": daily_revenue,
            "mpesaRevenue": mpesa_revenue, "cardRevenue": card_revenue,
            "deliveryCount": delivery_count, "pickupCount": pickup_count,
            "categoryBreakdown": category_breakdown, "topProducts": top_products,
        }