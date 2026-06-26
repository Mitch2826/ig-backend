"""
app/blueprints/admin/schemas.py
Marshmallow schemas for admin dashboard, inventory, settings, customers,
and reports — matches AdminDashboard.tsx, InventoryPage.tsx,
SettingsPage.tsx, CustomersPage.tsx, ReportsPage.tsx on the frontend.
"""

from marshmallow import Schema, fields, validate


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────
class DashboardMetricsSchema(Schema):
    revenueToday = fields.Float()
    ordersToday = fields.Int()
    totalCustomers = fields.Int()
    lowStockCount = fields.Int()


class RecentOrderSchema(Schema):
    id = fields.Str()
    customer = fields.Str()
    amount = fields.Float()
    status = fields.Str()
    itemsCount = fields.Int()
    paymentMethod = fields.Str()
    createdAt = fields.Str(allow_none=True)


class TopProductSchema(Schema):
    id = fields.Str()
    name = fields.Str()
    category = fields.Str(allow_none=True)
    unitsSold = fields.Int()
    revenue = fields.Float()
    stock = fields.Int()


class LowStockItemSchema(Schema):
    id = fields.Str()
    name = fields.Str()
    sku = fields.Str()
    stock = fields.Int()
    threshold = fields.Int()


class DashboardResponseSchema(Schema):
    metrics = fields.Nested(DashboardMetricsSchema)
    recentOrders = fields.List(fields.Nested(RecentOrderSchema))
    topProducts = fields.List(fields.Nested(TopProductSchema))
    lowStockItems = fields.List(fields.Nested(LowStockItemSchema))


# ─────────────────────────────────────────────────────────────────────────────
# Inventory
# ─────────────────────────────────────────────────────────────────────────────
class InventoryUpdateSchema(Schema):
    stock = fields.Int(required=False, validate=validate.Range(min=0))
    lowStockThreshold = fields.Int(required=False, validate=validate.Range(min=1))


class BulkInventoryUpdateSchema(Schema):
    productIds = fields.List(fields.Str(), required=True, validate=validate.Length(min=1))
    stock = fields.Int(required=True, validate=validate.Range(min=0))


# ─────────────────────────────────────────────────────────────────────────────
# Settings
# ─────────────────────────────────────────────────────────────────────────────
class FeatureFlagsSchema(Schema):
    salesAndDiscounts = fields.Bool(required=False)
    flashDealsSection = fields.Bool(required=False)
    freeDelivery = fields.Bool(required=False)
    googleAuth = fields.Bool(required=False)
    dynamicHero = fields.Bool(required=False)


class StoreSettingsSchema(Schema):
    storeName = fields.Str(required=False)
    storeAddress = fields.Str(required=False)
    storeHours = fields.Str(required=False)
    storePhone = fields.Str(required=False)
    supportEmail = fields.Email(required=False)
    deliveryFee = fields.Float(required=False, validate=validate.Range(min=0))
    minOrderAmount = fields.Float(required=False, validate=validate.Range(min=0))
    mpesaPaybill = fields.Str(required=False)
    mpesaAccountPrefix = fields.Str(required=False)
    freeDeliveryThreshold = fields.Float(required=False, validate=validate.Range(min=0))


class HeroSlideSchema(Schema):
    id = fields.Str(required=False)
    title = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    subtitle = fields.Str(required=False, allow_none=True)
    badge = fields.Str(required=False, allow_none=True)
    cta = fields.Str(required=False, load_default="Shop Now")
    ctaLink = fields.Str(required=False, load_default="/")
    image = fields.Str(required=False, allow_none=True)
    bgFrom = fields.Str(required=False, load_default="#1A5C38")
    bgTo = fields.Str(required=False, load_default="#0f3b22")
    isActive = fields.Bool(required=False, load_default=True)


# ─────────────────────────────────────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────────────────────────────────────
class CustomerListQuerySchema(Schema):
    search = fields.Str(required=False, load_default=None)
    tier = fields.Str(required=False, load_default="all", validate=validate.OneOf(["all", "new", "regular", "vip"]))
    page = fields.Int(required=False, load_default=1, validate=validate.Range(min=1))
    perPage = fields.Int(required=False, load_default=20, validate=validate.Range(min=1, max=100))


class CustomerResponseSchema(Schema):
    id = fields.Str()
    firstName = fields.Str()
    lastName = fields.Str()
    email = fields.Str()
    phone = fields.Str(allow_none=True)
    joinedAt = fields.Str(allow_none=True)
    totalOrders = fields.Int()
    totalSpent = fields.Float()
    lastOrderAt = fields.Str(allow_none=True)
    tier = fields.Str()


class CustomerListResponseSchema(Schema):
    items = fields.List(fields.Nested(CustomerResponseSchema))
    total = fields.Int()
    page = fields.Int()
    perPage = fields.Int()
    totalPages = fields.Int()


# ─────────────────────────────────────────────────────────────────────────────
# Reports
# ─────────────────────────────────────────────────────────────────────────────
class ReportsQuerySchema(Schema):
    range = fields.Str(required=False, load_default="7d", validate=validate.OneOf(["today", "7d", "30d", "90d"]))


class DailyRevenueSchema(Schema):
    date = fields.Str()
    revenue = fields.Float()
    orders = fields.Int()


class CategoryBreakdownSchema(Schema):
    category = fields.Str()
    revenue = fields.Float()
    percentage = fields.Float()


class ReportsResponseSchema(Schema):
    totalRevenue = fields.Float()
    totalOrders = fields.Int()
    avgOrderValue = fields.Float()
    dailyRevenue = fields.List(fields.Nested(DailyRevenueSchema))
    mpesaRevenue = fields.Float()
    cardRevenue = fields.Float()
    deliveryCount = fields.Int()
    pickupCount = fields.Int()
    categoryBreakdown = fields.List(fields.Nested(CategoryBreakdownSchema))
    topProducts = fields.List(fields.Nested(TopProductSchema))


class MessageSchema(Schema):
    message = fields.Str()