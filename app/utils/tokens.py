"""
app/utils/tokens.py
Generates and verifies time-limited, signed tokens for password reset.
Uses itsdangerous (already a Flask dependency, no new package needed) —
the token encodes the user's email and is signed with SECRET_KEY, so it
can't be forged, and it expires automatically after EXPIRY_SECONDS.
"""

from itsdangerous import URLSafeTimedSerializer
from flask import current_app

RESET_PASSWORD_SALT = "password-reset"
RESET_PASSWORD_EXPIRY_SECONDS = 3600  # 1 hour — matches common practice for reset links


def _get_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"])


def generate_reset_token(email: str) -> str:
    return _get_serializer().dumps(email, salt=RESET_PASSWORD_SALT)


def verify_reset_token(token: str):
    """Returns the email if valid and not expired, else None."""
    try:
        email = _get_serializer().loads(
            token, salt=RESET_PASSWORD_SALT, max_age=RESET_PASSWORD_EXPIRY_SECONDS
        )
        return email
    except Exception:
        return None