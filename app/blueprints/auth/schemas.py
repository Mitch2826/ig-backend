"""
app/blueprints/auth/schemas.py
Marshmallow schemas for auth endpoints.
Field names match what RegisterPage.tsx and LoginPage.tsx send (camelCase).
"""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError


class RegisterSchema(Schema):
    firstName = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    lastName = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    email = fields.Email(required=True)
    phone = fields.Str(required=False, allow_none=True, load_default=None)
    password = fields.Str(required=True, validate=validate.Length(min=8), load_only=True)

    # DPA 2019 consent checkbox — matches the RegisterPage.tsx consent
    # snippet we added to the frontend. Required to be True, not just present.
    agreedToTerms = fields.Bool(required=True)

    @validates_schema
    def validate_consent(self, data, **kwargs):
        if not data.get("agreedToTerms"):
            raise ValidationError(
                "You must agree to the Terms of Service and Privacy Policy",
                field_name="agreedToTerms",
            )


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True, load_only=True)


class RefreshResponseSchema(Schema):
    accessToken = fields.Str()


class AuthResponseSchema(Schema):
    accessToken = fields.Str()
    refreshToken = fields.Str()
    user = fields.Dict()  # shaped by User.to_dict() — kept loose here intentionally


class ForgotPasswordSchema(Schema):
    email = fields.Email(required=True)


class ResetPasswordSchema(Schema):
    token = fields.Str(required=True)
    newPassword = fields.Str(required=True, validate=validate.Length(min=8), load_only=True)


class MessageSchema(Schema):
    message = fields.Str()