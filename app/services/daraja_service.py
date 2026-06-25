"""
app/services/daraja_service.py
Safaricom Daraja API integration for M-Pesa STK Push.

Flow:
1. get_access_token() — OAuth token, cached in Redis for ~55 min (Daraja
   tokens last 1 hour; we refresh slightly early to avoid edge-case expiry).
2. initiate_stk_push() — sends the actual payment prompt to the customer's
   phone. Returns a CheckoutRequestID we store on the Payment record.
3. Safaricom calls OUR callback URL (DARAJA_CALLBACK_URL) asynchronously
   once the customer enters their PIN — that's handled in the Payments
   blueprint's routes.py, not here. This file only handles outbound calls
   to Safaricom.

Sandbox vs production: the only difference is the base URL and the actual
consumer key/secret/shortcode/passkey values in config — same code path
for both, controlled entirely by DARAJA_ENV.
"""

import base64
import json
from datetime import datetime

import requests
from flask import current_app

from app.extensions import redis_client

DARAJA_TOKEN_CACHE_KEY = "daraja:access_token"
DARAJA_TOKEN_CACHE_TTL = 3300  # 55 minutes — Daraja tokens last 60 min


def _base_url() -> str:
    if current_app.config["DARAJA_ENV"] == "production":
        return "https://api.safaricom.co.ke"
    return "https://sandbox.safaricom.co.ke"


def get_access_token() -> str:
    """
    Fetches an OAuth access token from Daraja, cached in Redis to avoid
    requesting a new one on every single payment (Safaricom rate-limits
    this endpoint, and tokens are valid for an hour anyway).
    Falls back to fetching fresh every time if Redis is unavailable.
    """
    if redis_client:
        cached = redis_client.get(DARAJA_TOKEN_CACHE_KEY)
        if cached:
            return cached

    consumer_key = current_app.config["DARAJA_CONSUMER_KEY"]
    consumer_secret = current_app.config["DARAJA_CONSUMER_SECRET"]

    response = requests.get(
        f"{_base_url()}/oauth/v1/generate?grant_type=client_credentials",
        auth=(consumer_key, consumer_secret),
        timeout=10,
    )
    response.raise_for_status()
    token = response.json()["access_token"]

    if redis_client:
        redis_client.set(DARAJA_TOKEN_CACHE_KEY, token, ex=DARAJA_TOKEN_CACHE_TTL)

    return token


def _generate_password(shortcode: str, passkey: str, timestamp: str) -> str:
    raw = f"{shortcode}{passkey}{timestamp}"
    return base64.b64encode(raw.encode()).decode()


def initiate_stk_push(phone: str, amount: float, order_id: str) -> dict:
    """
    Sends an STK Push prompt to the customer's phone.

    phone: must be in format 254712345678 (no +, no leading 0)
    amount: whole shillings (Daraja sandbox doesn't accept decimals reliably)
    order_id: used as the AccountReference so the customer's M-Pesa
              statement shows which order this payment was for

    Returns the raw Daraja response dict, which includes CheckoutRequestID —
    store this on the Payment record so we can match the async callback
    back to the right order.

    Raises requests.HTTPError if Daraja rejects the request outright
    (e.g. bad credentials, malformed phone). Does NOT mean the customer's
    payment failed — that result only comes later via the callback.
    """
    token = get_access_token()
    shortcode = current_app.config["DARAJA_SHORTCODE"]
    passkey = current_app.config["DARAJA_PASSKEY"]
    callback_url = current_app.config["DARAJA_CALLBACK_URL"]

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = _generate_password(shortcode, passkey, timestamp)

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": int(round(amount)),
        "PartyA": phone,
        "PartyB": shortcode,
        "PhoneNumber": phone,
        "CallBackURL": callback_url,
        "AccountReference": order_id,
        "TransactionDesc": f"Payment for order {order_id}",
    }

    response = requests.post(
        f"{_base_url()}/mpesa/stkpush/v1/processrequest",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def query_stk_status(checkout_request_id: str) -> dict:
    """
    Manually queries the status of an STK Push — useful as a fallback if
    the callback never arrives (e.g. customer's network dropped) so we're
    not stuck waiting forever. Can be called from a scheduled job
    (Phase 5) for any payment stuck in 'pending' for more than a few minutes.
    """
    token = get_access_token()
    shortcode = current_app.config["DARAJA_SHORTCODE"]
    passkey = current_app.config["DARAJA_PASSKEY"]

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = _generate_password(shortcode, passkey, timestamp)

    payload = {
        "BusinessShortCode": shortcode,
        "Password": password,
        "Timestamp": timestamp,
        "CheckoutRequestID": checkout_request_id,
    }

    response = requests.post(
        f"{_base_url()}/mpesa/stkpushquery/v1/query",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def parse_callback(callback_body: dict) -> dict:
    """
    Parses the raw callback payload Safaricom POSTs to our DARAJA_CALLBACK_URL
    into a clean shape. Daraja's callback structure is deeply nested and
    inconsistent between success/failure, so this isolates that mess from
    the route handler.

    Returns:
        {
            "checkout_request_id": str,
            "success": bool,
            "result_code": int,
            "result_desc": str,
            "mpesa_receipt_number": str | None,  # only present on success
            "amount": float | None,
            "phone": str | None,
        }
    """
    stk_callback = callback_body.get("Body", {}).get("stkCallback", {})
    checkout_request_id = stk_callback.get("CheckoutRequestID")
    result_code = stk_callback.get("ResultCode")
    result_desc = stk_callback.get("ResultDesc", "")

    success = result_code == 0

    mpesa_receipt_number = None
    amount = None
    phone = None

    if success:
        # On success, the actual payment details are buried in a list of
        # {Name, Value} pairs under CallbackMetadata — Safaricom's API design,
        # not ours. We extract the fields we care about by name.
        metadata_items = (
            stk_callback.get("CallbackMetadata", {}).get("Item", [])
        )
        metadata = {item.get("Name"): item.get("Value") for item in metadata_items}
        mpesa_receipt_number = metadata.get("MpesaReceiptNumber")
        amount = metadata.get("Amount")
        phone = metadata.get("PhoneNumber")

    return {
        "checkout_request_id": checkout_request_id,
        "success": success,
        "result_code": result_code,
        "result_desc": result_desc,
        "mpesa_receipt_number": mpesa_receipt_number,
        "amount": amount,
        "phone": phone,
    }