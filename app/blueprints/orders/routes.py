"""
app/blueprints/orders/routes.py
PLACEHOLDER — order placement, status updates, cancellation/return requests come next.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("orders", __name__, url_prefix="/api/orders", description="Orders")


@blp.route("/")
class OrderList(MethodView):
    def get(self):
        return {"message": "Orders endpoint — full implementation coming next"}