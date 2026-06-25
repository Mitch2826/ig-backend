"""
app/blueprints/users/schemas.py
Marshmallow schemas for user profile management and DPA 2019 compliance
endpoints (data export, account deletion request) — matches what was
promised in the frontend's PrivacyPolicyPage.tsx ("Right to access",
"Right to deletion", "Data portability").
"""

from marshmallow import Schema, fields, validate


class ProfileResponseSchema(Schema):
    id = fields.Str()
    firstName = fields.Str()
    lastName = fields.Str()
    email = fields.Str()
    phone = fields.Str(allow_none=True)
    role = fields.Str()
    isActive = fields.Bool()


class ProfileUpdateSchema(Schema):
    firstName = fields.Str(required=False, validate=validate.Length(min=1, max=80))
    lastName = fields.Str(required=False, validate=validate.Length(min=1, max=80))
    phone = fields.Str(required=False, allow_none=True)


class ChangePasswordSchema(Schema):
    currentPassword = fields.Str(required=True, load_only=True)
    newPassword = fields.Str(required=True, validate=validate.Length(min=8), load_only=True)


class DataExportResponseSchema(Schema):
    """Matches DPA 2019 Right to Data Portability — a structured,
    machine-readable export of everything we hold about the user."""
    profile = fields.Dict()
    orders = fields.List(fields.Dict())
    exportedAt = fields.Str()


class DeletionRequestResponseSchema(Schema):
    message = fields.Str()
    requestedAt = fields.Str()


class MessageSchema(Schema):
    message = fields.Str()