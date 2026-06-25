"""
app/blueprints/payments/routes.py
PLACEHOLDER — Daraja STK Push and iPay/Pesapal integration come later (Phase 3).
"""

from flask.views import MethodView
from flask_smorest import Blueprint

blp = Blueprint("payments", __name__, url_prefix="/api/payments", description="Payments")


@blp.route("/")
class PaymentIndex(MethodView):
    def get(self):
        return {"message": "Payments endpoint — full implementation coming in Phase 3"}