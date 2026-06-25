"""
app/blueprints/products/routes.py
PLACEHOLDER — full CRUD, search, filter, pagination comes next.
Minimal blueprint registered now so the app boots and /docs shows the route exists.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("products", __name__, url_prefix="/api/products", description="Product catalog")


@blp.route("/")
class ProductList(MethodView):
    def get(self):
        return {"message": "Products endpoint — full implementation coming next"}