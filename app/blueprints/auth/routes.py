"""
app/blueprints/auth/routes.py
Authentication endpoints: register, login, token refresh, logout, password reset.

Role assignment note: new registrations via POST /api/auth/register are
ALWAYS created with role='customer'. Admin, store_manager, and
delivery_agent accounts are never self-registered — admin/store_manager
accounts are created directly in the database (or via a future seed/admin
tool), and delivery_agent accounts are created through the Delivery
blueprint's agent management endpoints (see AgentManagement.tsx on the
frontend, which explicitly creates a login account for new agents).
"""

from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, get_jwt_identity,
)

from app.extensions import db, limiter
from app.models import User
from app.utils.tokens import generate_reset_token, verify_reset_token
from app.blueprints.auth.schemas import (
    RegisterSchema, LoginSchema, AuthResponseSchema, RefreshResponseSchema,
    ForgotPasswordSchema, ResetPasswordSchema, MessageSchema,
)

blp = Blueprint("auth", __name__, url_prefix="/api/auth", description="Authentication")


def _make_tokens(user):
    # Role is embedded in the token claims so decorators in
    # app/utils/decorators.py can check it without a DB lookup on every request
    additional_claims = {"role": user.role}
    access_token = create_access_token(identity=user.id, additional_claims=additional_claims)
    refresh_token = create_refresh_token(identity=user.id, additional_claims=additional_claims)
    return access_token, refresh_token


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/register
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/register")
class Register(MethodView):
    @limiter.limit("10 per hour")  # prevent registration spam/abuse
    @blp.arguments(RegisterSchema)
    @blp.response(201, AuthResponseSchema)
    def post(self, data):
        if User.query.filter_by(email=data["email"].lower()).first():
            abort(409, message="An account with this email already exists")

        user = User(
            first_name=data["firstName"],
            last_name=data["lastName"],
            email=data["email"].lower(),
            phone=data.get("phone"),
            role="customer",  # always — see module docstring
            agreed_to_terms=True,
            agreed_to_terms_at=datetime.now(timezone.utc),
        )
        user.set_password(data["password"])

        db.session.add(user)
        db.session.commit()

        access_token, refresh_token = _make_tokens(user)
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user.to_dict(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/login
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/login")
class Login(MethodView):
    @limiter.limit("20 per hour")  # slow down brute-force attempts
    @blp.arguments(LoginSchema)
    @blp.response(200, AuthResponseSchema)
    def post(self, data):
        user = User.query.filter_by(email=data["email"].lower()).first()

        # Deliberately vague error message — doesn't reveal whether the
        # email exists, which is standard practice against account enumeration
        if not user or not user.check_password(data["password"]):
            abort(401, message="Invalid email or password")

        if not user.is_active:
            abort(403, message="This account has been deactivated. Contact support.")

        access_token, refresh_token = _make_tokens(user)
        return {
            "accessToken": access_token,
            "refreshToken": refresh_token,
            "user": user.to_dict(),
        }


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/refresh
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/refresh")
class Refresh(MethodView):
    @jwt_required(refresh=True)  # must present a REFRESH token, not an access token
    @blp.response(200, RefreshResponseSchema)
    def post(self):
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        if not user or not user.is_active:
            abort(401, message="Account no longer valid")

        additional_claims = {"role": user.role}
        new_access_token = create_access_token(identity=user.id, additional_claims=additional_claims)
        return {"accessToken": new_access_token}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/logout
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/logout")
class Logout(MethodView):
    @jwt_required()
    @blp.response(200, MessageSchema)
    def post(self):
        # Stateless JWT — there's no server-side session to destroy.
        # The frontend's job is to discard the tokens from storage.
        # If we later need server-side invalidation (e.g. "log out all
        # devices"), this is where a token blocklist in Redis would go.
        return {"message": "Logged out successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/forgot-password
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/forgot-password")
class ForgotPassword(MethodView):
    @limiter.limit("5 per hour")
    @blp.arguments(ForgotPasswordSchema)
    @blp.response(200, MessageSchema)
    def post(self, data):
        user = User.query.filter_by(email=data["email"].lower()).first()

        # Always return the same response whether or not the email exists —
        # prevents leaking which emails are registered
        if user:
            token = generate_reset_token(user.email)
            reset_link = f"https://iandg.co.ke/reset-password?token={token}"

            # TODO (Phase 5): replace this print with an actual email send
            # via app/services/email_service.py once Mailtrap/SES is wired up.
            # For now this lets us test the full flow manually using the
            # token printed to the Flask console.
            print(f"[DEV] Password reset link for {user.email}: {reset_link}")

        return {"message": "If that email is registered, a reset link has been sent."}


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/auth/reset-password
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/reset-password")
class ResetPassword(MethodView):
    @limiter.limit("10 per hour")
    @blp.arguments(ResetPasswordSchema)
    @blp.response(200, MessageSchema)
    def post(self, data):
        email = verify_reset_token(data["token"])
        if not email:
            abort(400, message="This reset link is invalid or has expired")

        user = User.query.filter_by(email=email).first()
        if not user:
            abort(400, message="This reset link is invalid or has expired")

        user.set_password(data["newPassword"])
        db.session.commit()

        return {"message": "Password has been reset successfully"}