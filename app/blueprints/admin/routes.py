"""
app/blueprints/admin/routes.py
PLACEHOLDER — dashboard metrics, inventory, settings, customers, reports come next.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("admin", __name__, url_prefix="/api/admin", description="Admin operations")


@blp.route("/")
class AdminIndex(MethodView):
    def get(self):
        return {"message": "Admin endpoint — full implementation coming next"}