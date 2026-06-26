"""
app/blueprints/delivery/schemas.py
Marshmallow schemas for delivery agent management (admin side) and the
agent's own dashboard (matches AgentManagement.tsx and DeliveryDashboard.tsx).
"""

from marshmallow import Schema, fields, validate


# ─────────────────────────────────────────────────────────────────────────────
# Admin — agent CRUD
# ─────────────────────────────────────────────────────────────────────────────
class AgentCreateSchema(Schema):
    name = fields.Str(required=True, validate=validate.Length(min=1, max=160))
    phone = fields.Str(required=True, validate=validate.Regexp(r"^\+254\d{9}$", error="Use format +254712345678"))
    email = fields.Email(required=True)
    vehicleType = fields.Str(
        required=False, load_default="motorcycle",
        validate=validate.OneOf(["motorcycle", "bicycle", "car", "on_foot"]),
    )
    idNumber = fields.Str(required=True, validate=validate.Length(min=1, max=30))


class AgentUpdateSchema(Schema):
    name = fields.Str(required=False, validate=validate.Length(min=1, max=160))
    phone = fields.Str(required=False, validate=validate.Regexp(r"^\+254\d{9}$", error="Use format +254712345678"))
    email = fields.Email(required=False)
    vehicleType = fields.Str(required=False, validate=validate.OneOf(["motorcycle", "bicycle", "car", "on_foot"]))
    idNumber = fields.Str(required=False, validate=validate.Length(min=1, max=30))
    isActive = fields.Bool(required=False)


class AgentResponseSchema(Schema):
    id = fields.Str()
    name = fields.Str(allow_none=True)
    phone = fields.Str(allow_none=True)
    email = fields.Str(allow_none=True)
    vehicleType = fields.Str()
    idNumber = fields.Str()
    status = fields.Str()
    isActive = fields.Bool()
    activeDeliveries = fields.Int()
    joinedAt = fields.Str(allow_none=True)
    temporaryPassword = fields.Str(required=False)  # only present in create response


class AgentCreatedResponseSchema(AgentResponseSchema):
    temporaryPassword = fields.Str()


# ─────────────────────────────────────────────────────────────────────────────
# Admin — order assignment
# ─────────────────────────────────────────────────────────────────────────────
class AssignOrderSchema(Schema):
    agentId = fields.Str(required=True)


class DeliveryOrderResponseSchema(Schema):
    id = fields.Str()
    customer = fields.Str()
    phone = fields.Str()
    address = fields.Str(allow_none=True)
    zone = fields.Str(allow_none=True)
    total = fields.Float()
    status = fields.Str()
    assignedAgent = fields.Str(allow_none=True)
    createdAt = fields.Str(allow_none=True)


# ─────────────────────────────────────────────────────────────────────────────
# Agent's own dashboard
# ─────────────────────────────────────────────────────────────────────────────
class MyDeliveryResponseSchema(Schema):
    id = fields.Str()
    customer = fields.Str()
    phone = fields.Str()
    address = fields.Str(allow_none=True)
    zone = fields.Str(allow_none=True)
    total = fields.Float()
    items = fields.Int()
    status = fields.Str()
    assignedAt = fields.Str(allow_none=True)


class AgentStatusUpdateSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(["available", "busy", "offline"]))


class MessageSchema(Schema):
    message = fields.Str()