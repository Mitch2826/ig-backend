"""
app/blueprints/orders/schemas.py
Marshmallow schemas for order endpoints.

PlaceOrderSchema matches what CheckoutPage.tsx sends at the final "Place
Order" step — delivery/pickup details, contact info, items, payment method.

Response schemas mirror Order.to_dict() (admin shape) and
Order.to_customer_dict() (customer shape) respectively.
"""

from marshmallow import Schema, fields, validate, validates_schema, ValidationError


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/orders — place a new order
# ─────────────────────────────────────────────────────────────────────────────
class OrderItemInputSchema(Schema):
    productId = fields.Str(required=True)
    quantity = fields.Int(required=True, validate=validate.Range(min=1))


class PlaceOrderSchema(Schema):
    items = fields.List(fields.Nested(OrderItemInputSchema), required=True, validate=validate.Length(min=1))

    fulfilmentType = fields.Str(required=True, validate=validate.OneOf(["delivery", "pickup"]))

    # Contact — always required regardless of fulfilment type
    firstName = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    lastName = fields.Str(required=True, validate=validate.Length(min=1, max=80))
    phone = fields.Str(required=True, validate=validate.Length(min=1, max=20))
    email = fields.Email(required=True)

    # Delivery address — required only when fulfilmentType == "delivery"
    zone = fields.Str(required=False, allow_none=True, load_default=None)
    estate = fields.Str(required=False, allow_none=True, load_default=None)
    street = fields.Str(required=False, allow_none=True, load_default=None)
    buildingApartment = fields.Str(required=False, allow_none=True, load_default=None)
    deliveryInstructions = fields.Str(required=False, allow_none=True, load_default=None)

    paymentMethod = fields.Str(required=True, validate=validate.OneOf(["mpesa", "debit_card"]))
    mpesaPhone = fields.Str(required=False, allow_none=True, load_default=None)

    @validates_schema
    def validate_delivery_fields(self, data, **kwargs):
        if data["fulfilmentType"] == "delivery":
            if not data.get("zone"):
                raise ValidationError("Delivery zone is required", field_name="zone")
            if not data.get("street"):
                raise ValidationError("Street is required", field_name="street")

        if data["paymentMethod"] == "mpesa" and not data.get("mpesaPhone"):
            raise ValidationError("M-Pesa phone number is required", field_name="mpesaPhone")


# ─────────────────────────────────────────────────────────────────────────────
# Response schemas
# ─────────────────────────────────────────────────────────────────────────────
class OrderItemResponseSchema(Schema):
    productId = fields.Str()
    quantity = fields.Int()
    price = fields.Float()
    name = fields.Str(allow_none=True)
    unit = fields.Str(allow_none=True)
    image = fields.Str(allow_none=True)


class DeliveryAddressResponseSchema(Schema):
    zone = fields.Str(allow_none=True)
    estate = fields.Str(allow_none=True)
    street = fields.Str(allow_none=True)
    building = fields.Str(allow_none=True)
    instructions = fields.Str(allow_none=True)


class CustomerInfoSchema(Schema):
    name = fields.Str()
    phone = fields.Str()
    email = fields.Str()


class ReturnRequestResponseSchema(Schema):
    reason = fields.Str()
    details = fields.Str(allow_none=True)
    status = fields.Str()
    requestedAt = fields.Str(allow_none=True)
    resolvedAt = fields.Str(allow_none=True)


class OrderResponseSchema(Schema):
    """Admin-facing shape — matches frontend AdminOrder interface."""
    id = fields.Str()
    customer = fields.Nested(CustomerInfoSchema)
    items = fields.List(fields.Nested(OrderItemResponseSchema))
    subtotal = fields.Float()
    deliveryFee = fields.Float()
    total = fields.Float()
    status = fields.Str()
    paymentMethod = fields.Str()
    paymentReference = fields.Str(allow_none=True)
    fulfilmentType = fields.Str()
    deliveryAddress = fields.Nested(DeliveryAddressResponseSchema, required=False)
    createdAt = fields.Str(allow_none=True)
    updatedAt = fields.Str(allow_none=True)
    assignedAgent = fields.Str(required=False)
    returnRequest = fields.Nested(ReturnRequestResponseSchema, required=False)


class MyOrderResponseSchema(Schema):
    """Customer-facing shape — matches frontend MyOrder interface."""
    id = fields.Str()
    items = fields.List(fields.Nested(OrderItemResponseSchema))
    subtotal = fields.Float()
    deliveryFee = fields.Float()
    total = fields.Float()
    status = fields.Str()
    createdAt = fields.Str(allow_none=True)
    deliveredAt = fields.Str(allow_none=True)
    canCancelInstantly = fields.Bool()
    hasReturnRequest = fields.Bool()
    fulfilmentType = fields.Str()
    paymentMethod = fields.Str()
    paymentReference = fields.Str(allow_none=True)


class OrderListResponseSchema(Schema):
    items = fields.List(fields.Nested(OrderResponseSchema))
    total = fields.Int()
    page = fields.Int()
    perPage = fields.Int()
    totalPages = fields.Int()


# ─────────────────────────────────────────────────────────────────────────────
# Query params for admin order list
# ─────────────────────────────────────────────────────────────────────────────
class OrderListQuerySchema(Schema):
    status = fields.Str(required=False, load_default="all")
    paymentMethod = fields.Str(required=False, load_default="all", validate=validate.OneOf(["all", "mpesa", "debit_card"]))
    search = fields.Str(required=False, load_default=None)
    page = fields.Int(required=False, load_default=1, validate=validate.Range(min=1))
    perPage = fields.Int(required=False, load_default=20, validate=validate.Range(min=1, max=100))


# ─────────────────────────────────────────────────────────────────────────────
# Status update / cancellation / return requests
# ─────────────────────────────────────────────────────────────────────────────
class StatusUpdateSchema(Schema):
    status = fields.Str(required=True)


class CancellationRequestSchema(Schema):
    reason = fields.Str(required=False, allow_none=True, load_default=None)


class ReturnRequestCreateSchema(Schema):
    reason = fields.Str(required=True, validate=validate.OneOf([
        "Item damaged or broken",
        "Item expired or near expiry",
        "Wrong item delivered",
        "Item missing from order",
        "Quality not as expected",
        "Other",
    ]))
    details = fields.Str(required=False, allow_none=True, load_default=None)


class ReturnResolveSchema(Schema):
    status = fields.Str(required=True, validate=validate.OneOf(["approved", "declined"]))


class MessageSchema(Schema):
    message = fields.Str()