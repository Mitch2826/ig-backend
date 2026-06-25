"""
app/blueprints/delivery/routes.py
PLACEHOLDER — agent CRUD, order assignment, agent's own dashboard come next.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("delivery", __name__, url_prefix="/api/delivery", description="Delivery management")


@blp.route("/")
class DeliveryIndex(MethodView):
    def get(self):
        return {"message": "Delivery endpoint — full implementation coming next"}