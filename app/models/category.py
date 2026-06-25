import uuid
from datetime import datetime, timezone
from app.extensions import db


def _uuid():
    return str(uuid.uuid4())


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    name = db.Column(db.String(120), nullable=False, unique=True)
    slug = db.Column(db.String(120), nullable=False, unique=True, index=True)

    # Iconify icon name, e.g. "noto:shopping-cart" — matches frontend's
    # category.illustration field used with the <Icon> component
    illustration = db.Column(db.String(100), nullable=False, default="noto:shopping-cart")

    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # ── Relationships ────────────────────────────────────────────────────────
    subcategories = db.relationship(
        "Subcategory", back_populates="category",
        cascade="all, delete-orphan", order_by="Subcategory.display_order",
    )
    products = db.relationship("Product", back_populates="category")

    # ── Serialization — matches frontend Category interface ─────────────────
    def to_dict(self, include_product_count=False):
        data = {
            "id": self.id,
            "name": self.name,
            "slug": self.slug,
            "illustration": self.illustration,
            "isActive": self.is_active,
            "subcategories": [s.to_dict() for s in self.subcategories],
        }
        if include_product_count:
            # Only count active products so deactivated/deleted ones
            # don't inflate the number shown in the admin CategoriesPage
            data["productCount"] = sum(1 for p in self.products if p.is_active)
        return data

    def __repr__(self):
        return f"<Category {self.name}>"


class Subcategory(db.Model):
    __tablename__ = "subcategories"

    id = db.Column(db.String(36), primary_key=True, default=_uuid)
    category_id = db.Column(db.String(36), db.ForeignKey("categories.id"), nullable=False)

    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)

    # ── Relationships ────────────────────────────────────────────────────────
    category = db.relationship("Category", back_populates="subcategories")

    __table_args__ = (
        # A subcategory slug only needs to be unique within its parent category,
        # not globally — e.g. "snacks" could exist under two different categories.
        db.UniqueConstraint("category_id", "slug", name="uq_subcategory_slug_per_category"),
    )

    # ── Serialization — matches frontend Subcategory { name, slug } ─────────
    def to_dict(self):
        return {"name": self.name, "slug": self.slug}

    def __repr__(self):
        return f"<Subcategory {self.name}>"