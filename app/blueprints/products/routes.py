"""
app/blueprints/products/routes.py
Product catalog endpoints.

Public endpoints (storefront):
    GET  /api/products/            list with search/filter/sort/pagination
    GET  /api/products/<id>        single product detail

Admin/store_manager endpoints:
    GET    /api/products/admin/all               list including inactive
    POST   /api/products/admin                    create
    PATCH  /api/products/admin/<id>                update
    DELETE /api/products/admin/<id>                delete (admin only)
    POST   /api/products/admin/<id>/images         upload image to Cloudinary
    DELETE /api/products/admin/<id>/images/<img_id> remove an image
    PATCH  /api/products/admin/<id>/images/<img_id>/primary  set as primary
"""

from flask import request
from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import or_

from app.extensions import db
from app.models import Product, ProductImage, Category, AuditLog
from app.utils.decorators import staff_only, admin_only
from app.services.settings_service import get_feature_flag
from app.services.image_service import upload_product_image, delete_product_image
from app.blueprints.products.schemas import (
    ProductListQuerySchema, ProductResponseSchema, ProductListResponseSchema,
    ProductCreateSchema, ProductUpdateSchema, ProductImageResponseSchema, MessageSchema,
)

blp = Blueprint("products", __name__, url_prefix="/api/products", description="Product catalog")


def _apply_sale_price() -> bool:
    """Controlled by the same flag the frontend reads (FEATURES.SALES_AND_DISCOUNTS)."""
    return get_feature_flag("feature.sales_and_discounts")


def _get_stock_status(product: Product) -> str:
    if product.available_stock == 0:
        return "out_of_stock"
    if product.available_stock <= product.low_stock_threshold:
        return "low_stock"
    return "in_stock"


def _log_admin_action(user_id, action, resource_id, details=None):
    db.session.add(AuditLog(
        user_id=user_id, action=action, resource_type="product",
        resource_id=resource_id, details=details,
    ))


def _sort_and_paginate(items, sort_key_map, args):
    sort_fn = sort_key_map.get(args["sort"], sort_key_map["name"])
    items.sort(key=sort_fn, reverse=(args["dir"] == "desc"))

    total = len(items)
    start = (args["page"] - 1) * args["perPage"]
    end = start + args["perPage"]
    page_items = items[start:end]

    return page_items, total


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/products/  — public, list with search/filter/sort/pagination
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/")
class ProductList(MethodView):
    @blp.arguments(ProductListQuerySchema, location="query")
    @blp.response(200, ProductListResponseSchema)
    def get(self, args):
        query = Product.query.filter(Product.is_active.is_(True))

        if args["search"]:
            term = f"%{args['search']}%"
            query = query.filter(
                or_(Product.name.ilike(term), Product.brand.ilike(term), Product.sku.ilike(term))
            )

        if args["category"]:
            query = query.join(Category).filter(Category.slug == args["category"])

        if args["subcategory"]:
            query = query.filter(Product.subcategory_name == args["subcategory"])

        if args["featured"] is not None:
            query = query.filter(Product.is_featured.is_(args["featured"]))

        if args["flashDeal"] is not None:
            query = query.filter(Product.is_flash_deal.is_(args["flashDeal"]))

        all_matching = query.all()

        if args["stock"] != "all":
            all_matching = [p for p in all_matching if _get_stock_status(p) == args["stock"]]

        apply_sale = _apply_sale_price()
        sort_key_map = {
            "name": lambda p: p.name.lower(),
            "price": lambda p: float(p.effective_price if apply_sale else p.price),
            "stock": lambda p: p.available_stock,
            "category": lambda p: (p.category.name.lower() if p.category else ""),
            "newest": lambda p: p.created_at,
        }
        page_items, total = _sort_and_paginate(all_matching, sort_key_map, args)

        return {
            "items": [p.to_dict(apply_sale_price=apply_sale) for p in page_items],
            "total": total,
            "page": args["page"],
            "perPage": args["perPage"],
            "totalPages": max(1, (total + args["perPage"] - 1) // args["perPage"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/products/<id>  — public, single product
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/<string:product_id>")
class ProductDetail(MethodView):
    @blp.response(200, ProductResponseSchema)
    def get(self, product_id):
        product = Product.query.get(product_id)
        if not product or not product.is_active:
            abort(404, message="Product not found")
        return product.to_dict(apply_sale_price=_apply_sale_price())


# ─────────────────────────────────────────────────────────────────────────────
# Admin — list (includes inactive, always shows salePrice)
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/all")
class AdminProductList(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(ProductListQuerySchema, location="query")
    @blp.response(200, ProductListResponseSchema)
    def get(self, args):
        query = Product.query

        if args["status"] == "active":
            query = query.filter(Product.is_active.is_(True))
        elif args["status"] == "inactive":
            query = query.filter(Product.is_active.is_(False))

        if args["search"]:
            term = f"%{args['search']}%"
            query = query.filter(
                or_(Product.name.ilike(term), Product.brand.ilike(term), Product.sku.ilike(term))
            )

        if args["category"]:
            query = query.join(Category).filter(Category.slug == args["category"])

        all_matching = query.all()

        if args["stock"] != "all":
            all_matching = [p for p in all_matching if _get_stock_status(p) == args["stock"]]

        sort_key_map = {
            "name": lambda p: p.name.lower(),
            "price": lambda p: float(p.price),
            "stock": lambda p: p.available_stock,
            "category": lambda p: (p.category.name.lower() if p.category else ""),
            "newest": lambda p: p.created_at,
        }
        page_items, total = _sort_and_paginate(all_matching, sort_key_map, args)

        return {
            "items": [p.to_dict(apply_sale_price=True) for p in page_items],
            "total": total,
            "page": args["page"],
            "perPage": args["perPage"],
            "totalPages": max(1, (total + args["perPage"] - 1) // args["perPage"]),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Admin — create
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin")
class ProductCreate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(ProductCreateSchema)
    @blp.response(201, ProductResponseSchema)
    def post(self, data):
        category = Category.query.filter_by(name=data["category"]).first()
        if not category:
            abort(400, message=f"Category '{data['category']}' does not exist")

        if Product.query.filter_by(sku=data["sku"]).first():
            abort(409, message=f"SKU '{data['sku']}' is already in use")

        product = Product(
            name=data["name"], brand=data["brand"], description=data["description"],
            category_id=category.id, subcategory_name=data["subcategory"],
            price=data["price"], sale_price=data.get("salePrice"),
            unit=data["unit"], sku=data["sku"], stock=data["stock"],
            low_stock_threshold=data.get("lowStockThreshold", 5),
            ingredients=data.get("ingredients"), tags=data.get("tags", []),
            nutrition_info=data.get("nutritionInfo", []),
            is_featured=data.get("isFeatured", False), is_flash_deal=data.get("isFlashDeal", False),
            flash_deal_ends_at=data.get("flashDealEndsAt"), is_active=data.get("isActive", True),
        )
        db.session.add(product)
        db.session.flush()

        _log_admin_action(get_jwt_identity(), "product.created", product.id,
                           {"name": product.name, "sku": product.sku})
        db.session.commit()

        return product.to_dict(apply_sale_price=True)


# ─────────────────────────────────────────────────────────────────────────────
# Admin — update / delete
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:product_id>")
class ProductUpdate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(ProductUpdateSchema)
    @blp.response(200, ProductResponseSchema)
    def patch(self, data, product_id):
        product = Product.query.get(product_id)
        if not product:
            abort(404, message="Product not found")

        changes = {}

        if "category" in data:
            category = Category.query.filter_by(name=data["category"]).first()
            if not category:
                abort(400, message=f"Category '{data['category']}' does not exist")
            if category.id != product.category_id:
                changes["category"] = {
                    "from": product.category.name if product.category else None,
                    "to": category.name,
                }
            product.category_id = category.id

        if "sku" in data and data["sku"] != product.sku:
            if Product.query.filter(Product.sku == data["sku"], Product.id != product_id).first():
                abort(409, message=f"SKU '{data['sku']}' is already in use")
            changes["sku"] = {"from": product.sku, "to": data["sku"]}
            product.sku = data["sku"]

        if "price" in data and float(data["price"]) != float(product.price):
            changes["price"] = {"from": float(product.price), "to": data["price"]}
            product.price = data["price"]

        simple_fields = {
            "name": "name", "brand": "brand", "description": "description",
            "subcategory": "subcategory_name", "unit": "unit", "stock": "stock",
            "lowStockThreshold": "low_stock_threshold", "ingredients": "ingredients",
            "tags": "tags", "nutritionInfo": "nutrition_info",
            "isFeatured": "is_featured", "isFlashDeal": "is_flash_deal",
            "flashDealEndsAt": "flash_deal_ends_at", "isActive": "is_active",
            "salePrice": "sale_price",
        }
        for input_key, model_attr in simple_fields.items():
            if input_key in data:
                setattr(product, model_attr, data[input_key])

        if changes:
            _log_admin_action(get_jwt_identity(), "product.updated", product.id, changes)

        db.session.commit()
        return product.to_dict(apply_sale_price=True)

    @jwt_required()
    @admin_only  # only admin can delete, not store_manager — matches frontend ProductsPage.tsx
    @blp.response(200, MessageSchema)
    def delete(self, product_id):
        product = Product.query.get(product_id)
        if not product:
            abort(404, message="Product not found")

        if product.order_items:
            # Don't hard-delete a product with order history — deactivate
            # instead so past orders/receipts still display correctly.
            product.is_active = False
            _log_admin_action(get_jwt_identity(), "product.deactivated", product.id,
                               {"reason": "has order history, soft-deleted instead"})
            db.session.commit()
            return {"message": "Product has order history — deactivated instead of deleted"}

        for image in product.images:
            delete_product_image(image.cloudinary_public_id)

        _log_admin_action(get_jwt_identity(), "product.deleted", product.id, {"name": product.name})
        db.session.delete(product)
        db.session.commit()
        return {"message": "Product deleted successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — image upload / delete / set primary
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/admin/<string:product_id>/images")
class ProductImageUpload(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(201, ProductImageResponseSchema)
    def post(self, product_id):
        product = Product.query.get(product_id)
        if not product:
            abort(404, message="Product not found")

        if "file" not in request.files:
            abort(400, message="No image file provided")

        file = request.files["file"]
        if file.filename == "":
            abort(400, message="No image file selected")

        if len(product.images) >= 6:
            abort(400, message="Maximum of 6 images per product")

        upload_result = upload_product_image(file, product_id)
        is_first_image = len(product.images) == 0

        image = ProductImage(
            product_id=product_id, url=upload_result["url"],
            cloudinary_public_id=upload_result["public_id"],
            is_primary=is_first_image, display_order=len(product.images),
        )
        db.session.add(image)
        db.session.commit()

        return {"url": image.url, "publicId": image.cloudinary_public_id, "isPrimary": image.is_primary}


@blp.route("/admin/<string:product_id>/images/<string:image_id>")
class ProductImageDelete(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, MessageSchema)
    def delete(self, product_id, image_id):
        image = ProductImage.query.filter_by(id=image_id, product_id=product_id).first()
        if not image:
            abort(404, message="Image not found")

        was_primary = image.is_primary
        delete_product_image(image.cloudinary_public_id)
        db.session.delete(image)
        db.session.flush()

        if was_primary:
            next_image = (
                ProductImage.query.filter_by(product_id=product_id)
                .order_by(ProductImage.display_order)
                .first()
            )
            if next_image:
                next_image.is_primary = True

        db.session.commit()
        return {"message": "Image deleted"}


@blp.route("/admin/<string:product_id>/images/<string:image_id>/primary")
class ProductImageSetPrimary(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, MessageSchema)
    def patch(self, product_id, image_id):
        target = ProductImage.query.filter_by(id=image_id, product_id=product_id).first()
        if not target:
            abort(404, message="Image not found")

        ProductImage.query.filter_by(product_id=product_id).update({"is_primary": False})
        target.is_primary = True
        db.session.commit()
        return {"message": "Primary image updated"}