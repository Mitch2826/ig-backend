"""
app/blueprints/users/routes.py
PLACEHOLDER — profile, DPA data export/deletion requests come later.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("users", __name__, url_prefix="/api/users", description="User account management")


@blp.route("/")
class UsersIndex(MethodView):
    def get(self):
        return {"message": "Users endpoint — full implementation coming next"}