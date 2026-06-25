"""
app/blueprints/auth/routes.py
PLACEHOLDER — real register/login/JWT/refresh logic comes next.
Minimal blueprint registered now so the app boots and /docs shows the route exists.
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("auth", __name__, url_prefix="/api/auth", description="Authentication")


@blp.route("/")
class AuthIndex(MethodView):
    def get(self):
        return {"message": "Auth endpoint — full implementation coming next"}