"""
app/blueprints/categories/routes.py
Category and Subcategory endpoints.

Public:
    GET /api/categories/          list all active categories (storefront navbar/homepage)
    GET /api/categories/<slug>    single category by slug (category page)

Admin/store_manager:
    GET    /api/categories/admin/all              list including inactive, with product counts
    POST   /api/categories/admin                   create category
    PATCH  /api/categories/admin/<id>               update category
    PATCH  /api/categories/admin/<id>/toggle-active toggle active/inactive
    DELETE /api/categories/admin/<id>               delete (admin only, blocked if has products)

    POST   /api/categories/admin/<id>/subcategories                  add subcategory
    PATCH  /api/categories/admin/<id>/subcategories/<sub_id>          update subcategory
    DELETE /api/categories/admin/<id>/subcategories/<sub_id>          delete subcategory
"""

import re
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import Category, Subcategory, AuditLog
from app.utils.decorators import staff_only, admin_only
from app.blueprints.categories.schemas import (
    CategoryResponseSchema, CategoryCreateSchema, CategoryUpdateSchema,
    SubcategoryCreateSchema, SubcategoryUpdateSchema, MessageSchema,
)

blp = Blueprint("categories", __name__, url_prefix="/api/categories", description="Categories")


def _to_slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _log(user_id, action, resource_id, details=None):
    db.session.add(AuditLog(
        user_id=user_id, action=action, resource_type="category",
        resource_id=resource_id, details=details,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# Public — list active categories
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/")
class CategoryList(MethodView):
    @blp.response(200, CategoryResponseSchema(many=True))
    def get(self):
        categories = (
            Category.query.filter_by(is_active=True)
            .order_by(Category.display_order)
            .all()
        )
        return [c.to_dict() for c in categories]


# ─────────────────────────────────────────────────────────────────────────────
# Public — single category by slug
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:slug>")
class CategoryDetail(MethodView):
    @blp.response(200, CategoryResponseSchema)
    def get(self, slug):
        category = Category.query.filter_by(slug=slug, is_active=True).first()
        if not category:
            abort(404, message="Category not found")
        return category.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# Admin — list all (including inactive) with product counts
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/all")
class AdminCategoryList(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, CategoryResponseSchema(many=True))
    def get(self):
        categories = Category.query.order_by(Category.display_order).all()
        return [c.to_dict(include_product_count=True) for c in categories]


# ─────────────────────────────────────────────────────────────────────────────
# Admin — create category
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin")
class CategoryCreate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(CategoryCreateSchema)
    @blp.response(201, CategoryResponseSchema)
    def post(self, data):
        if Category.query.filter_by(name=data["name"]).first():
            abort(409, message=f"Category '{data['name']}' already exists")

        slug = data.get("slug") or _to_slug(data["name"])
        if Category.query.filter_by(slug=slug).first():
            abort(409, message=f"A category with slug '{slug}' already exists")

        category = Category(
            name=data["name"], slug=slug,
            illustration=data.get("illustration", "noto:shopping-cart"),
            is_active=data.get("isActive", True),
        )
        db.session.add(category)
        db.session.flush()

        _log(get_jwt_identity(), "category.created", category.id, {"name": category.name})
        db.session.commit()

        return category.to_dict(include_product_count=True)


# ─────────────────────────────────────────────────────────────────────────────
# Admin — update / delete category
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:category_id>")
class CategoryUpdate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(CategoryUpdateSchema)
    @blp.response(200, CategoryResponseSchema)
    def patch(self, data, category_id):
        category = Category.query.get(category_id)
        if not category:
            abort(404, message="Category not found")

        if "name" in data and data["name"] != category.name:
            if Category.query.filter(Category.name == data["name"], Category.id != category_id).first():
                abort(409, message=f"Category '{data['name']}' already exists")
            category.name = data["name"]

        if "slug" in data and data["slug"] != category.slug:
            if Category.query.filter(Category.slug == data["slug"], Category.id != category_id).first():
                abort(409, message=f"A category with slug '{data['slug']}' already exists")
            category.slug = data["slug"]

        if "illustration" in data:
            category.illustration = data["illustration"]

        if "isActive" in data:
            category.is_active = data["isActive"]

        _log(get_jwt_identity(), "category.updated", category.id, data)
        db.session.commit()

        return category.to_dict(include_product_count=True)

    @jwt_required()
    @admin_only  # admin only — matches frontend CategoriesPage.tsx delete button
    @blp.response(200, MessageSchema)
    def delete(self, category_id):
        category = Category.query.get(category_id)
        if not category:
            abort(404, message="Category not found")

        if category.products:
            abort(
                400,
                message=f"Cannot delete '{category.name}' — it has {len(category.products)} "
                        "product(s). Reassign or delete those products first.",
            )

        _log(get_jwt_identity(), "category.deleted", category.id, {"name": category.name})
        db.session.delete(category)  # cascades to subcategories
        db.session.commit()
        return {"message": "Category deleted successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — toggle active (quick action, separate from full update)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:category_id>/toggle-active")
class CategoryToggleActive(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, CategoryResponseSchema)
    def patch(self, category_id):
        category = Category.query.get(category_id)
        if not category:
            abort(404, message="Category not found")

        category.is_active = not category.is_active
        _log(get_jwt_identity(), "category.toggled_active", category.id,
             {"isActive": category.is_active})
        db.session.commit()

        return category.to_dict(include_product_count=True)


# ─────────────────────────────────────────────────────────────────────────────
# Admin — subcategory create
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:category_id>/subcategories")
class SubcategoryCreate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(SubcategoryCreateSchema)
    @blp.response(201, CategoryResponseSchema)
    def post(self, data, category_id):
        category = Category.query.get(category_id)
        if not category:
            abort(404, message="Category not found")

        slug = data.get("slug") or _to_slug(data["name"])

        # Slug only needs to be unique within this category (see model's
        # UniqueConstraint), so check scoped to category_id
        if Subcategory.query.filter_by(category_id=category_id, slug=slug).first():
            abort(409, message=f"A subcategory with slug '{slug}' already exists in this category")

        subcategory = Subcategory(
            category_id=category_id, name=data["name"], slug=slug,
            display_order=len(category.subcategories),
        )
        db.session.add(subcategory)

        _log(get_jwt_identity(), "subcategory.created", category_id, {"name": data["name"]})
        db.session.commit()

        return category.to_dict(include_product_count=True)


# ─────────────────────────────────────────────────────────────────────────────
# Admin — subcategory update / delete
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:category_id>/subcategories/<string:subcategory_id>")
class SubcategoryUpdate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(SubcategoryUpdateSchema)
    @blp.response(200, CategoryResponseSchema)
    def patch(self, data, category_id, subcategory_id):
        subcategory = Subcategory.query.filter_by(id=subcategory_id, category_id=category_id).first()
        if not subcategory:
            abort(404, message="Subcategory not found")

        if "name" in data:
            subcategory.name = data["name"]
        if "slug" in data and data["slug"] != subcategory.slug:
            if Subcategory.query.filter_by(category_id=category_id, slug=data["slug"]).first():
                abort(409, message=f"A subcategory with slug '{data['slug']}' already exists in this category")
            subcategory.slug = data["slug"]

        _log(get_jwt_identity(), "subcategory.updated", category_id, data)
        db.session.commit()

        return Category.query.get(category_id).to_dict(include_product_count=True)

    @jwt_required()
    @staff_only
    @blp.response(200, CategoryResponseSchema)
    def delete(self, category_id, subcategory_id):
        subcategory = Subcategory.query.filter_by(id=subcategory_id, category_id=category_id).first()
        if not subcategory:
            abort(404, message="Subcategory not found")

        # Check if any products use this subcategory (by name, since
        # Product.subcategory_name is a plain string, not an FK — see
        # the design note in app/models/product.py)
        from app.models import Product
        products_using_it = Product.query.filter_by(
            category_id=category_id, subcategory_name=subcategory.name
        ).count()
        if products_using_it > 0:
            abort(
                400,
                message=f"Cannot delete '{subcategory.name}' — {products_using_it} product(s) "
                        "use this subcategory. Reassign those products first.",
            )

        _log(get_jwt_identity(), "subcategory.deleted", category_id, {"name": subcategory.name})
        db.session.delete(subcategory)
        db.session.commit()

        return Category.query.get(category_id).to_dict(include_product_count=True)