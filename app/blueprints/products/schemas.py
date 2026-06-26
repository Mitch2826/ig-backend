"""
app/blueprints/products/schemas.py
Marshmallow schemas for product endpoints.

Output field names match the frontend Product interface in mockData.ts
exactly (camelCase) since Product.to_dict() already builds that shape.

Input field names (admin create/update) match what AddEditProductPage.tsx
sends.
"""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# Query params for GET /api/products
# ─────────────────────────────────────────────────────────────────────────────
class ProductListQuerySchema(Schema):
    search = fields.Str(required=False, load_default=None)
    category = fields.Str(required=False, load_default=None)       # category slug
    subcategory = fields.Str(required=False, load_default=None)
    stock = fields.Str(
        required=False, load_default="all",
        validate=validate.OneOf(["all", "in_stock", "low_stock", "out_of_stock"]),
    )
    status = fields.Str(
        required=False, load_default="active",
        validate=validate.OneOf(["all", "active", "inactive"]),
    )
    featured = fields.Bool(required=False, load_default=None)
    flashDeal = fields.Bool(required=False, load_default=None)
    sort = fields.Str(
        required=False, load_default="name",
        validate=validate.OneOf(["name", "price", "stock", "category", "newest"]),
    )
    dir = fields.Str(required=False, load_default="asc", validate=validate.OneOf(["asc", "desc"]))
    page = fields.Int(required=False, load_default=1, validate=validate.Range(min=1))
    perPage = fields.Int(required=False, load_default=24, validate=validate.Range(min=1, max=100))


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────
class ProductResponseSchema(Schema):
    id = fields.Str()
    name = fields.Str()
    brand = fields.Str()
    description = fields.Str()
    category = fields.Str()
    subcategory = fields.Str(allow_none=True)
    price = fields.Float()
    salePrice = fields.Float(allow_none=True)
    unit = fields.Str()
    sku = fields.Str()
    stock = fields.Int()
    lowStockThreshold = fields.Int()
    image = fields.Str(allow_none=True)
    images = fields.List(fields.Str())
    ingredients = fields.Str(allow_none=True)
    tags = fields.List(fields.Str())
    nutritionInfo = fields.List(fields.Dict())
    rating = fields.Float()
    reviewCount = fields.Int()
    isFeatured = fields.Bool()
    isFlashDeal = fields.Bool()
    flashDealEndsAt = fields.Str(allow_none=True)
    isActive = fields.Bool()


class ProductListResponseSchema(Schema):
    items = fields.List(fields.Nested(ProductResponseSchema))
    total = fields.Int()
    page = fields.Int()
    perPage = fields.Int()
    totalPages = fields.Int()


# ─────────────────────────────────────────────────────────────────────────────
# Admin create / update
# ─────────────────────────────────────────────────────────────────────────────
class ProductCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=200))
    brand = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    description = fields.Str(required=True, validate=validate.Length(min=1))

    category = fields.Str(required=True)        # category name
    subcategory = fields.Str(required=True)      # subcategory name

    price = fields.Float(required=True, validate=validate.Range(min=0.01))
    salePrice = fields.Float(required=False, allow_none=True, validate=validate.Range(min=0.01))
    unit = fields.Str(required=True)
    sku = fields.Str(required=True, validate=validate.Length(min=1, max=50))

    stock = fields.Int(required=True, validate=validate.Range(min=0))
    lowStockThreshold = fields.Int(required=False, load_default=5, validate=validate.Range(min=1))

    ingredients = fields.Str(required=False, allow_none=True, load_default=None)
    tags = fields.List(fields.Str(), required=False, load_default=list)
    nutritionInfo = fields.List(fields.Dict(), required=False, load_default=list)

    isFeatured = fields.Bool(required=False, load_default=False)
    isFlashDeal = fields.Bool(required=False, load_default=False)
    flashDealEndsAt = fields.DateTime(required=False, allow_none=True, load_default=None)
    isActive = fields.Bool(required=False, load_default=True)

    @validates_schema
    def validate_sale_price(self, data, **kwargs):
        sale_price = data.get("salePrice")
        price = data.get("price")
        if sale_price is not None and price is not None and sale_price >= price:
            raise ValidationError("salePrice must be less than price", field_name="salePrice")


class ProductUpdateSchema(ProductCreateSchema):
    """Same fields as create, but all optional since it's a partial update (PATCH)."""
    name = fields.Str(required=False, validate=validate.Length(min=1, max=200))
    brand = fields.Str(required=False, validate=validate.Length(min=1, max=120))
    description = fields.Str(required=False, validate=validate.Length(min=1))
    category = fields.Str(required=False)
    subcategory = fields.Str(required=False)
    price = fields.Float(required=False, validate=validate.Range(min=0.01))
    unit = fields.Str(required=False)
    sku = fields.Str(required=False, validate=validate.Length(min=1, max=50))
    stock = fields.Int(required=False, validate=validate.Range(min=0))


class ProductImageResponseSchema(Schema):
    url = fields.Str()
    publicId = fields.Str()
    isPrimary = fields.Bool()


class MessageSchema(Schema):
    message = fields.Str()