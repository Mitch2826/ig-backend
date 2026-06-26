"""
app/blueprints/delivery/routes.py
Delivery agent management (admin/store_manager) and the agent's own
dashboard (delivery_agent role).

Admin/store_manager endpoints:
    GET    /api/delivery/agents                list all agents
    POST   /api/delivery/agents                 create agent (creates User + DeliveryAgent together)
    PATCH  /api/delivery/agents/<id>             update agent
    DELETE /api/delivery/agents/<id>             remove agent (deactivates if has order history)

    GET    /api/delivery/orders                 list orders needing/with delivery assignment
    PATCH  /api/delivery/orders/<id>/assign       assign an order to an agent

Delivery agent's own endpoints:
    GET    /api/delivery/my-orders               own assigned active deliveries
    PATCH  /api/delivery/my-orders/<id>/delivered  mark a delivery complete
    PATCH  /api/delivery/my-status                update own availability status
"""

import secrets
import string
from datetime import datetime, timezone

from flask.views import MethodView
from flask_smorest import Blueprint, abort
from flask_jwt_extended import jwt_required, get_jwt_identity

from app.extensions import db
from app.models import User, DeliveryAgent, Order, AuditLog
from app.utils.decorators import staff_only, delivery_agent_only
from app.services.email_service import send_agent_welcome_email
from app.services.sms_service import send_agent_assignment_sms
from app.blueprints.delivery.schemas import (
    AgentCreateSchema, AgentUpdateSchema, AgentResponseSchema, AgentCreatedResponseSchema,
    AssignOrderSchema, DeliveryOrderResponseSchema, MyDeliveryResponseSchema,
    AgentStatusUpdateSchema, MessageSchema,
)

blp = Blueprint("delivery", __name__, url_prefix="/api/delivery", description="Delivery management")


def _log(user_id, action, resource_type, resource_id=None, details=None):
    db.session.add(AuditLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=resource_id, details=details,
    ))


def _generate_temp_password() -> str:
    """8-character random password for new agent accounts. Sent to them
    via the email confirmation flow (Phase 5) — for now, returned directly
    in the API response so admin can communicate it manually until email
    sending is wired up."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(10))


# ─────────────────────────────────────────────────────────────────────────────
# Admin — list agents
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/agents")
class AgentList(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, AgentResponseSchema(many=True))
    def get(self):
        agents = DeliveryAgent.query.all()
        return [a.to_dict() for a in agents]

    # ─────────────────────────────────────────────────────────────────────────
    # Admin — create agent. THIS IS THE KEY ENDPOINT that closes the gap
    # identified during frontend planning: creating an agent here creates
    # BOTH a User (role='delivery_agent', so they can log in) AND a
    # DeliveryAgent profile (vehicle, ID number, status) in one transaction.
    # ─────────────────────────────────────────────────────────────────────────
    @jwt_required()
    @staff_only
    @blp.arguments(AgentCreateSchema)
    @blp.response(201, AgentCreatedResponseSchema)
    def post(self, data):
        if User.query.filter_by(email=data["email"].lower()).first():
            abort(409, message="An account with this email already exists")

        name_parts = data["name"].strip().split(" ", 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ""

        temp_password = _generate_temp_password()

        user = User(
            first_name=first_name, last_name=last_name,
            email=data["email"].lower(), phone=data["phone"],
            role="delivery_agent",
            agreed_to_terms=True, agreed_to_terms_at=datetime.now(timezone.utc),
        )
        user.set_password(temp_password)
        db.session.add(user)
        db.session.flush()  # get user.id before creating the linked profile

        agent = DeliveryAgent(
            user_id=user.id, vehicle_type=data.get("vehicleType", "motorcycle"),
            id_number=data["idNumber"], status="offline",
        )
        db.session.add(agent)
        db.session.flush()

        _log(get_jwt_identity(), "agent.created", "delivery_agent", agent.id,
             {"name": data["name"], "email": data["email"]})
        db.session.commit()

        # Email the credentials directly now that email_service is wired up.
        # Still returned in the API response too as a fallback in case the
        # email fails to send or lands in spam — admin can communicate it
        # manually if needed.
        send_agent_welcome_email(data["email"], data["name"], temp_password)

        result = agent.to_dict()
        result["temporaryPassword"] = temp_password
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Admin — update / delete agent
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/agents/<string:agent_id>")
class AgentUpdate(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(AgentUpdateSchema)
    @blp.response(200, AgentResponseSchema)
    def patch(self, data, agent_id):
        agent = DeliveryAgent.query.get(agent_id)
        if not agent:
            abort(404, message="Agent not found")

        if "name" in data:
            name_parts = data["name"].strip().split(" ", 1)
            agent.user.first_name = name_parts[0]
            agent.user.last_name = name_parts[1] if len(name_parts) > 1 else ""

        if "phone" in data:
            agent.user.phone = data["phone"]

        if "email" in data and data["email"].lower() != agent.user.email:
            if User.query.filter(User.email == data["email"].lower(), User.id != agent.user_id).first():
                abort(409, message="An account with this email already exists")
            agent.user.email = data["email"].lower()

        if "vehicleType" in data:
            agent.vehicle_type = data["vehicleType"]
        if "idNumber" in data:
            agent.id_number = data["idNumber"]
        if "isActive" in data:
            agent.is_active = data["isActive"]
            agent.user.is_active = data["isActive"]  # deactivating agent also blocks their login

        _log(get_jwt_identity(), "agent.updated", "delivery_agent", agent.id, data)
        db.session.commit()
        return agent.to_dict()

    @jwt_required()
    @staff_only
    @blp.response(200, MessageSchema)
    def delete(self, agent_id):
        agent = DeliveryAgent.query.get(agent_id)
        if not agent:
            abort(404, message="Agent not found")

        if agent.assigned_orders:
            # Don't hard-delete an agent with delivery history — deactivate
            # both the agent profile and their login instead.
            agent.is_active = False
            agent.user.is_active = False
            agent.status = "offline"
            _log(get_jwt_identity(), "agent.deactivated", "delivery_agent", agent.id,
                 {"reason": "has delivery history, deactivated instead of deleted"})
            db.session.commit()
            return {"message": "Agent has delivery history — deactivated instead of removed"}

        _log(get_jwt_identity(), "agent.deleted", "delivery_agent", agent.id,
             {"name": f"{agent.user.first_name} {agent.user.last_name}"})
        db.session.delete(agent)
        db.session.delete(agent.user)
        db.session.commit()
        return {"message": "Agent removed successfully"}


# ─────────────────────────────────────────────────────────────────────────────
# Admin — list orders needing/with delivery assignment
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/orders")
class DeliveryOrderList(MethodView):
    @jwt_required()
    @staff_only
    @blp.response(200, DeliveryOrderResponseSchema(many=True))
    def get(self):
        orders = (
            Order.query.filter(
                Order.fulfilment_type == "delivery",
                Order.status.in_(["processing", "out_for_delivery"]),
            )
            .order_by(Order.created_at)
            .all()
        )

        result = []
        for o in orders:
            address_parts = [o.delivery_street, o.delivery_estate, o.delivery_zone]
            address = ", ".join(p for p in address_parts if p)
            result.append({
                "id": o.id,
                "customer": f"{o.contact_first_name} {o.contact_last_name}",
                "phone": o.contact_phone,
                "address": address or None,
                "zone": o.delivery_zone,
                "total": float(o.total),
                "status": "assigned" if o.assigned_agent_id else "awaiting_assignment",
                "assignedAgent": (
                    f"{o.assigned_agent.user.first_name} {o.assigned_agent.user.last_name}"
                    if o.assigned_agent else None
                ),
                "createdAt": o.created_at.isoformat() if o.created_at else None,
            })
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Admin — assign an order to an agent
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/orders/<string:order_id>/assign")
class AssignOrder(MethodView):
    @jwt_required()
    @staff_only
    @blp.arguments(AssignOrderSchema)
    @blp.response(200, MessageSchema)
    def patch(self, data, order_id):
        order = Order.query.get(order_id)
        if not order:
            abort(404, message="Order not found")

        agent = DeliveryAgent.query.get(data["agentId"])
        if not agent or not agent.is_active:
            abort(404, message="Agent not found or inactive")

        order.assigned_agent_id = agent.id
        if order.status == "processing":
            order.status = "out_for_delivery"

        if agent.status == "available":
            agent.status = "busy"

        _log(get_jwt_identity(), "order.assigned", "order", order.id,
             {"agentId": agent.id, "agentName": f"{agent.user.first_name} {agent.user.last_name}"})
        db.session.commit()

        if agent.user.phone:
            send_agent_assignment_sms(agent.user.phone, order.id)

        return {"message": f"Order assigned to {agent.user.first_name} {agent.user.last_name}"}


# ─────────────────────────────────────────────────────────────────────────────
# Agent's own dashboard — GET /api/delivery/my-orders
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/my-orders")
class MyDeliveries(MethodView):
    @jwt_required()
    @delivery_agent_only
    @blp.response(200, MyDeliveryResponseSchema(many=True))
    def get(self):
        user_id = get_jwt_identity()
        agent = DeliveryAgent.query.filter_by(user_id=user_id).first()
        if not agent:
            abort(404, message="Delivery agent profile not found")

        orders = (
            Order.query.filter_by(assigned_agent_id=agent.id)
            .order_by(Order.created_at.desc())
            .all()
        )

        result = []
        for o in orders:
            address_parts = [o.delivery_street, o.delivery_estate, o.delivery_zone]
            address = ", ".join(p for p in address_parts if p)
            result.append({
                "id": o.id,
                "customer": f"{o.contact_first_name} {o.contact_last_name}",
                "phone": o.contact_phone,
                "address": address or None,
                "zone": o.delivery_zone,
                "total": float(o.total),
                "items": sum(i.quantity for i in o.items),
                "status": o.status,
                "assignedAt": o.updated_at.isoformat() if o.updated_at else None,
            })
        return result


# ─────────────────────────────────────────────────────────────────────────────
# Agent marks a delivery complete
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/my-orders/<string:order_id>/delivered")
class MarkDelivered(MethodView):
    @jwt_required()
    @delivery_agent_only
    @blp.response(200, MessageSchema)
    def patch(self, order_id):
        user_id = get_jwt_identity()
        agent = DeliveryAgent.query.filter_by(user_id=user_id).first()
        if not agent:
            abort(404, message="Delivery agent profile not found")

        order = Order.query.filter_by(id=order_id, assigned_agent_id=agent.id).first()
        if not order:
            abort(404, message="Order not found or not assigned to you")

        if order.status != "out_for_delivery":
            abort(400, message="Only orders that are out for delivery can be marked delivered")

        order.status = "delivered"
        order.delivered_at = datetime.now(timezone.utc)

        # Free up the agent if this was their last active delivery
        remaining = Order.query.filter(
            Order.assigned_agent_id == agent.id,
            Order.status.in_(["out_for_delivery", "processing"]),
        ).count()
        if remaining == 0:
            agent.status = "available"

        db.session.commit()
        return {"message": "Order marked as delivered"}


# ─────────────────────────────────────────────────────────────────────────────
# Agent updates own availability status
# ─────────────────────────────────────────────────────────────────────────────
@blp.route("/my-status")
class MyStatus(MethodView):
    @jwt_required()
    @delivery_agent_only
    @blp.arguments(AgentStatusUpdateSchema)
    @blp.response(200, MessageSchema)
    def patch(self, data):
        user_id = get_jwt_identity()
        agent = DeliveryAgent.query.filter_by(user_id=user_id).first()
        if not agent:
            abort(404, message="Delivery agent profile not found")

        agent.status = data["status"]
        db.session.commit()
        return {"message": f"Status updated to {data['status']}"}