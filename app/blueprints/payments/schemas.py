"""
app/blueprints/payments/schemas.py
Marshmallow schemas for payment initiation and status checking.
"""

from marshmallow import Schema, fields, validate


class InitiateMpesaPaymentSchema(Schema):
    orderId = fields.Str(required=True)
    phone = fields.Str(required=True, validate=validate.Length(min=9, max=13))


class PaymentResponseSchema(Schema):
    id = fields.Str()
    orderId = fields.Str()
    method = fields.Str()
    type = fields.Str()
    status = fields.Str()
    amount = fields.Float()
    reference = fields.Str(allow_none=True)
    mpesaReceiptNumber = fields.Str(allow_none=True)
    cardTransactionRef = fields.Str(allow_none=True)
    failureReason = fields.Str(allow_none=True)
    initiatedAt = fields.Str(allow_none=True)
    completedAt = fields.Str(allow_none=True)


class InitiateMpesaResponseSchema(Schema):
    paymentId = fields.Str()
    checkoutRequestId = fields.Str()
    customerMessage = fields.Str()


class PaymentStatusQuerySchema(Schema):
    paymentId = fields.Str(required=True)


class MessageSchema(Schema):
    message = fields.Str()