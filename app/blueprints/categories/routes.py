"""
app/blueprints/categories/routes.py
PLACEHOLDER — full CRUD comes next.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("categories", __name__, url_prefix="/api/categories", description="Categories")


@blp.route("/")
class CategoryList(MethodView):
    def get(self):
        return {"message": "Categories endpoint — full implementation coming next"}