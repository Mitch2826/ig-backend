"""
app/models/product.py
Product and ProductImage — matches the frontend Product interface in
mockData.ts exactly (camelCase on the to_dict() output).

Key design decisions:
- price/sale_price stored as Numeric (not Float) to avoid floating point
  rounding errors with currency.
- stock vs available_stock: `stock` is total physical stock, `reserved_stock`
  is units currently held by in-progress checkouts (paid-pending-confirmation).
  available_stock = stock - reserved_stock. This is the mechanism that
  prevents overselling, which was flagged as a gap during frontend planning.
- salePrice is only exposed in to_dict() when apply_sale_price=True, which
  the route layer controls based on the FEATURES.SALES_AND_DISCOUNTS flag.
"""

import uuid
from datetime import datetime, timezone
from app.extensions import db


def _uuid():
    return str(uuid.uuid4())


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)

    name = db.Column(db.String(200), nullable=False, index=True)
    brand = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)

    category_id = db.Column(db.String(36), db.ForeignKey("categories.id"), nullable=False)
    # Subcategory stored as plain text rather than FK — matches frontend
    # mockData.ts where subcategory is just { name, slug } embedded under
    # category, not a separately queryable global entity.
    subcategory_name = db.Column(db.String(120), nullable=True)

    price = db.Column(db.Numeric(10, 2), nullable=False)
    sale_price = db.Column(db.Numeric(10, 2), nullable=True)

    unit = db.Column(db.String(50), nullable=False)  # e.g. "per 2kg", "per piece"
    sku = db.Column(db.String(50), nullable=False, unique=True, index=True)

    stock = db.Column(db.Integer, nullable=False, default=0)
    reserved_stock = db.Column(db.Integer, nullable=False, default=0)
    low_stock_threshold = db.Column(db.Integer, nullable=False, default=5)

    ingredients = db.Column(db.Text, nullable=True)
    tags = db.Column(db.JSON, nullable=False, default=list)            # ["Organic", "Vegan"]
    nutrition_info = db.Column(db.JSON, nullable=False, default=list)  # [{label, value}]

    rating = db.Column(db.Numeric(2, 1), nullable=False, default=0)
    review_count = db.Column(db.Integer, nullable=False, default=0)

    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    is_flash_deal = db.Column(db.Boolean, default=False, nullable=False)
    flash_deal_ends_at = db.Column(db.DateTime, nullable=True)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    category = db.relationship("Category", back_populates="products")
    images = db.relationship(
        "ProductImage", back_populates="product",
        cascade="all, delete-orphan", order_by="ProductImage.display_order",
    )
    order_items = db.relationship("OrderItem", back_populates="product")

    # ── Computed properties ──────────────────────────────────────────────────
    @property
    def available_stock(self) -> int:
        """Stock actually purchasable right now — total minus what's
        reserved by other customers' in-progress checkouts."""
        return max(0, self.stock - self.reserved_stock)

    @property
    def effective_price(self):
        """The price to charge — sale_price if one is set, else regular price.
        Does NOT check the feature flag; that's the route layer's job via
        apply_sale_price in to_dict(). This property is used internally for
        actual order calculations regardless of what's displayed."""
        return self.sale_price if self.sale_price is not None else self.price

    @property
    def stock_status(self) -> str:
        if self.available_stock == 0:
            return "out_of_stock"
        if self.available_stock <= self.low_stock_threshold:
            return "low_stock"
        return "in_stock"

    @property
    def primary_image_url(self):
        primary = next((img for img in self.images if img.is_primary), None)
        if primary:
            return primary.url
        return self.images[0].url if self.images else None

    # ── Serialization — matches frontend Product interface (camelCase) ──────
    def to_dict(self, apply_sale_price: bool = False):
        data = {
            "id": self.id,
            "name": self.name,
            "brand": self.brand,
            "description": self.description,
            "category": self.category.name if self.category else None,
            "subcategory": self.subcategory_name,
            "price": float(self.price),
            "unit": self.unit,
            "sku": self.sku,
            "stock": self.available_stock,
            "lowStockThreshold": self.low_stock_threshold,
            "image": self.primary_image_url,
            "images": [img.url for img in self.images],
            "ingredients": self.ingredients,
            "tags": self.tags or [],
            "nutritionInfo": self.nutrition_info or [],
            "rating": float(self.rating),
            "reviewCount": self.review_count,
            "isFeatured": self.is_featured,
            "isFlashDeal": self.is_flash_deal,
            "flashDealEndsAt": (
                self.flash_deal_ends_at.isoformat() if self.flash_deal_ends_at else None
            ),
            "isActive": self.is_active,
        }
        # Only expose salePrice when the caller has confirmed the
        # SALES_AND_DISCOUNTS feature flag is on (admin always sees it
        # regardless — that's handled by the route, not here)
        data["salePrice"] = float(self.sale_price) if (apply_sale_price and self.sale_price) else None
        return data

    def __repr__(self):
        return f"<Product {self.sku} {self.name}>"


class ProductImage(db.Model):
    __tablename__ = "product_images"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    product_id = db.Column(db.String(36), db.ForeignKey("products.id"), nullable=False)

    url = db.Column(db.String(500), nullable=False)
    cloudinary_public_id = db.Column(db.String(255), nullable=True)  # needed to delete from Cloudinary

    is_primary = db.Column(db.Boolean, default=False, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # ── Relationships ────────────────────────────────────────────────────────
    product = db.relationship("Product", back_populates="images")

    def __repr__(self):
        return f"<ProductImage {self.id} primary={self.is_primary}>"