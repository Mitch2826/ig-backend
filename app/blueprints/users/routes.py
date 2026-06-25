"""
app/blueprints/users/routes.py
User profile management and DPA 2019 compliance endpoints.

    GET    /api/users/me                 own profile
    PATCH  /api/users/me                  update own profile
    PATCH  /api/users/me/password          change own password
    GET    /api/users/me/data-export       DPA Right to Data Portability
    POST   /api/users/me/deletion-request  DPA Right to Deletion

Note on deletion: we do NOT hard-delete immediately. The Privacy Policy
(see PrivacyPolicyPage.tsx Section 6 - Data Retention) commits to
retaining transaction records for up to 7 years to comply with KRA/tax
obligations. Submitting a deletion request deactivates the account
(blocks login, removes from active customer lists) and logs the request
for an admin/legal process to action the actual data purge later, scoped
to what's legally permissible to delete vs what must be retained.
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import User, AuditLog
from app.blueprints.users.schemas import (
    ProfileResponseSchema, ProfileUpdateSchema, ChangePasswordSchema,
    DataExportResponseSchema, DeletionRequestResponseSchema, MessageSchema,
)

blp = Blueprint("users", __name__, url_prefix="/api/users", description="User account management")


def _log(user_id, action, resource_type, resource_id=None, details=None):
    db.session.add(AuditLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=resource_id, details=details,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# GET / PATCH /api/users/me
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/me")
class MyProfile(MethodView):
    @jwt_required()
    @blp.response(200, ProfileResponseSchema)
    def get(self):
        user = User.query.get(get_jwt_identity())
        if not user:
            abort(404, message="User not found")
        return user.to_dict()

    @jwt_required()
    @blp.arguments(ProfileUpdateSchema)
    @blp.response(200, ProfileResponseSchema)
    def patch(self, data):
        user = User.query.get(get_jwt_identity())
        if not user:
            abort(404, message="User not found")

        if "firstName" in data:
            user.first_name = data["firstName"]
        if "lastName" in data:
            user.last_name = data["lastName"]
        if "phone" in data:
            user.phone = data["phone"]

        db.session.commit()
        return user.to_dict()


# ─────────────────────────────────────────────────────────────────────────────
# PATCH /api/users/me/password
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/me/password")
class ChangePassword(MethodView):
    @jwt_required()
    @blp.arguments(ChangePasswordSchema)
    @blp.response(200, MessageSchema)
    def patch(self, data):
        user = User.query.get(get_jwt_identity())
        if not user:
            abort(404, message="User not found")

        if not user.check_password(data["currentPassword"]):
            abort(401, message="Current password is incorrect")

        user.set_password(data["newPassword"])
        db.session.commit()
        return {"message": "Password updated successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# GET /api/users/me/data-export — DPA Right to Data Portability
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/me/data-export")
class DataExport(MethodView):
    @jwt_required()
    @blp.response(200, DataExportResponseSchema)
    def get(self):
        user = User.query.get(get_jwt_identity())
        if not user:
            abort(404, message="User not found")

        orders_data = [order.to_customer_dict() for order in user.orders]

        _log(user.id, "user.data_exported", "user", user.id,
             {"note": "Customer downloaded their own data export"})
        db.session.commit()

        return {
            "profile": user.to_dict(include_sensitive=True),
            "orders": orders_data,
            "exportedAt": datetime.now(timezone.utc).isoformat(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/users/me/deletion-request — DPA Right to Deletion
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/me/deletion-request")
class DeletionRequest(MethodView):
    @jwt_required()
    @blp.response(200, DeletionRequestResponseSchema)
    def post(self):
        user = User.query.get(get_jwt_identity())
        if not user:
            abort(404, message="User not found")

        if not user.is_active:
            abort(400, message="This account is already deactivated")

        # Deactivate immediately (blocks login, removes from active
        # customer lists/reports) — actual data purge is a manual/legal
        # process scoped to what's permissible to delete vs what must be
        # retained for tax/audit purposes (see Privacy Policy Section 6).
        user.is_active = False
        requested_at = datetime.now(timezone.utc)

        _log(user.id, "user.deletion_requested", "user", user.id,
            {"requestedAt": requested_at.isoformat(),
                "note": "Account deactivated immediately; data purge pending manual review "
                        "per retention policy"})
        db.session.commit()

        return {
            "message": "Your account has been deactivated and your deletion request has "
                        "been logged. Some data may be retained as required by law "
                        "(e.g. transaction records for tax purposes) — see our Privacy Policy "
                        "for details.",
            "requestedAt": requested_at.isoformat(),
        }