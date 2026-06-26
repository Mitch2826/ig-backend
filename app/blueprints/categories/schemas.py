"""
app/blueprints/categories/schemas.py
Marshmallow schemas for category/subcategory endpoints.
Matches the frontend CategoriesPage.tsx admin UI and the public
category strip in Navbar.tsx / HomePage.tsx.
"""

from marshmallow import Schema, fields, validate


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────
class SubcategoryResponseSchema(Schema):
    name = fields.Str()
    slug = fields.Str()


class CategoryResponseSchema(Schema):
    id = fields.Str()
    name = fields.Str()
    slug = fields.Str()
    illustration = fields.Str()
    isActive = fields.Bool()
    subcategories = fields.List(fields.Nested(SubcategoryResponseSchema))
    productCount = fields.Int(required=False)


class MessageSchema(Schema):
    message = fields.Str()


# ─────────────────────────────────────────────────────────────────────────────
# Admin create / update — category
# ─────────────────────────────────────────────────────────────────────────────
class CategoryCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    slug = fields.Str(required=False, allow_none=True, load_default=None)  # auto-generated if omitted
    illustration = fields.Str(required=False, load_default="noto:shopping-cart")
    isActive = fields.Bool(required=False, load_default=True)


class CategoryUpdateSchema(Schema):
    name = fields.Str(required=False, validate=validate.Length(min=1, max=120))
    slug = fields.Str(required=False)
    illustration = fields.Str(required=False)
    isActive = fields.Bool(required=False)


# ─────────────────────────────────────────────────────────────────────────────
# Admin create / update — subcategory
# ─────────────────────────────────────────────────────────────────────────────
class SubcategoryCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=120))
    slug = fields.Str(required=False, allow_none=True, load_default=None)


class SubcategoryUpdateSchema(Schema):
    name = fields.Str(required=False, validate=validate.Length(min=1, max=120))
    slug = fields.Str(required=False)