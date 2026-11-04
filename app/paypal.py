import logging

logger = logging.getLogger(__name__)

import os
import time
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

PAYPAL_CLIENT_ID = os.getenv("PAYPAL_CLIENT_ID")
PAYPAL_CLIENT_SECRET = os.getenv("PAYPAL_CLIENT_SECRET")
PAYPAL_API_BASE = os.getenv("PAYPAL_API_BASE", "https://api-m.sandbox.paypal.com")

MOCK_MODE = not (PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET)
logger.info("PayPal client initialized (mock_mode=%s)", MOCK_MODE)

_token_cache = {"access_token": None, "expires_at": 0.0}

async def get_access_token() ->str:
    if _token_cache["access_token"] and _token_cache["expires_at"] > time.time():
        return _token_cache["access_token"]

    logger.info("Fetching new PayPal OAuth token")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v1/oauth2/token",
            data = {"grant_type": "client_credentials"},
            auth = (PAYPAL_CLIENT_ID, PAYPAL_CLIENT_SECRET)
        )
        _raise_for_status(resp)
        data = resp.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data["expires_in"] - 60
    return data["access_token"]

async def _auth_headers() -> dict:
    token = await get_access_token()
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

def _raise_for_status(resp: httpx.Response) -> None:
    if resp.status_code >= 400:
        logger.error("PayPal API error %s: %s", resp.status_code, resp.text)
    resp.raise_for_status()

_mock_invoices = {
    "INV-1001": {
        "id": "INV-1001",
        "recipient_email": "client.one@example.com",
        "recipient_name": "Client One",
        "amount": 1200.00,
        "currency": "USD",
        "due_date": "2026-09-15",
        "status": "SENT",
        "reminders_sent": 0,
    },
    "INV-1002": {
        "id": "INV-1002",
        "recipient_email": "client.two@example.com",
        "recipient_name": "Client Two",
        "amount": 450.00,
        "currency": "USD",
        "due_date": "2026-10-01",
        "status": "SENT",
        "reminders_sent": 1,
    },
    "INV-1003": {
        "id": "INV-1003",
        "recipient_email": "client.three@example.com",
        "recipient_name": "Client Three",
        "amount": 3000.00,
        "currency": "USD",
        "due_date": "2026-10-20",
        "status": "SENT",
        "reminders_sent": 0,
    },
}

_mock_disputes = {
    "DIS-5001": {
        "id": "DIS-5001",
        "invoice_id": "INV-1002",
        "reason": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "status": "WAITING_FOR_SELLER_RESPONSE",
        "dispute_amount": 450.00,
        "currency": "USD",
        "messages": [
            {"from": "buyer", "text": "I never received the deliverable."}
        ],
    }
}


async def list_invoices() -> list[dict]:
    logger.info("list_invoices called (mock_mode=%s)", MOCK_MODE)
    if MOCK_MODE:
        return list(_mock_invoices.values())

    headers = await _auth_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{PAYPAL_API_BASE}/v2/invoicing/invoices", headers=headers)
        _raise_for_status(resp)
        return [_normalize_invoice(item) for item in resp.json().get("items", [])]


async def create_invoice(
    recipient_email: str,
    recipient_name: str,
    amount: float,
    currency: str,
    due_date: str,
    items: Optional[list[dict]] = None,
) -> dict:
    logger.info("create_invoice called for %s", recipient_email)
    if MOCK_MODE:
        new_id = f"INV-{1000 + len(_mock_invoices) + 1}"
        invoice = {
            "id": new_id,
            "recipient_email": recipient_email,
            "recipient_name": recipient_name,
            "amount": amount,
            "currency": currency,
            "due_date": due_date,
            "status": "DRAFT",
            "reminders_sent": 0,
        }
        _mock_invoices[new_id] = invoice
        return invoice

    name_parts = recipient_name.strip().split(" ", 1)
    given_name = name_parts[0]
    surname = name_parts[1] if len(name_parts) > 1 else ""

    headers = await _auth_headers()
    payload = {
        "detail": {
            "currency_code": currency,
            "payment_term": {"term_type": "DUE_ON_DATE_SPECIFIED", "due_date": due_date},
        },
        "invoicer": {},
        "primary_recipients": [
            {"billing_info": {"email_address": recipient_email, "name": {"given_name": given_name, "surname": surname}}}
        ],
        "items": items or [
            {"name": "Services rendered", "quantity": "1", "unit_amount": {"currency_code": currency, "value": str(amount)}}
        ],
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{PAYPAL_API_BASE}/v2/invoicing/invoices", headers=headers, json=payload)
        _raise_for_status(resp)
        return _normalize_invoice(resp.json())


async def send_invoice(invoice_id: str) -> dict:
    logger.info("send_invoice called for %s", invoice_id)
    if MOCK_MODE:
        invoice = _mock_invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Unknown invoice: {invoice_id}")
        invoice["status"] = "SENT"
        return invoice

    headers = await _auth_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{PAYPAL_API_BASE}/v2/invoicing/invoices/{invoice_id}/send", headers=headers)
        _raise_for_status(resp)
        return {"id": invoice_id, "status": "SENT"}


async def send_reminder(invoice_id: str) -> dict:
    logger.info("send_reminder called for %s", invoice_id)
    if MOCK_MODE:
        invoice = _mock_invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Unknown invoice: {invoice_id}")
        invoice["reminders_sent"] += 1
        return invoice

    headers = await _auth_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"{PAYPAL_API_BASE}/v2/invoicing/invoices/{invoice_id}/remind", headers=headers)
        _raise_for_status(resp)
        return {"id": invoice_id, "reminder_sent": True}


async def list_disputes() -> list[dict]:
    logger.info("list_disputes called (mock_mode=%s)", MOCK_MODE)
    if MOCK_MODE:
        return list(_mock_disputes.values())

    headers = await _auth_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{PAYPAL_API_BASE}/v1/customer/disputes", headers=headers)
        _raise_for_status(resp)
        return resp.json().get("items", [])


async def get_dispute(dispute_id: str) -> dict:
    logger.info("get_dispute called for %s", dispute_id)
    if MOCK_MODE:
        dispute = _mock_disputes.get(dispute_id)
        if not dispute:
            raise ValueError(f"Unknown dispute: {dispute_id}")
        return dispute

    headers = await _auth_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{PAYPAL_API_BASE}/v1/customer/disputes/{dispute_id}", headers=headers)
        _raise_for_status(resp)
        return resp.json()

async def delete_invoice(invoice_id: str) -> dict:
    logger.info("delete_invoice called for %s", invoice_id)
    if MOCK_MODE:
        invoice = _mock_invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Unknown invoice: {invoice_id}")
        if invoice["status"]!= "DRAFT":
            raise ValueError(f"Cannot delete invoice {invoice_id}:  not in DRAFT status (status={invoice['status']})")
        del _mock_invoices[invoice_id]
        return {"id": invoice_id, "deleted": True}

    headers = await _auth_headers()
    async with httpx.AsyncClient() as client:
        resp = await client.delete(f"{PAYPAL_API_BASE}/v2/invoicing/invoices/{invoice_id}", headers=headers)
        _raise_for_status(resp)
        return {"id": invoice_id, "deleted": True}

async def cancel_invoice(invoice_id: str, note: str = "") -> dict:
    logger.info("cancel_invoice called for %s", invoice_id)
    if MOCK_MODE:
        invoice = _mock_invoices.get(invoice_id)
        if not invoice:
            raise ValueError(f"Unknown invoice: {invoice_id}")
        if invoice["status"] == "DRAFT":
            raise ValueError(f"Cannot cancel invoice {invoice_id}: it's still a draft, delete it instead")
        invoice["status"] = "CANCELLED"
        return invoice

    headers = await _auth_headers()
    payload = {
        "subject": "Invoice cancelled",
        "note": note or "This invoice has been cancelled",
        "send_to_invoicer": True,
        "send_to_recipient": True,
    }

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{PAYPAL_API_BASE}/v2/invoicing/invoices/{invoice_id}/cancel",
            headers=headers,
            json = payload
        )
        _raise_for_status(resp)
        return {"id": invoice_id, "status": "CANCELLED"}

def _normalize_invoice(raw: dict) -> dict:
    detail = raw.get("detail", {})
    recipients = raw.get("primary_recipients", [])
    billing_info = recipients[0].get("billing_info", {}) if recipients else {}
    name_obj = billing_info.get("name", {})
    recipient_name = (
        name_obj.get("full_name")
        or " ".join(filter(None, [name_obj.get("given_name"), name_obj.get("surname")]))
        or billing_info.get("email_address", "Unknown")
    )

    amount = raw.get("amount", {})
    due_date = detail.get("payment_term", {}).get("due_date") or detail.get("invoice_date")

    return {
        "id": raw.get("id"),
        "recipient_email": billing_info.get("email_address"),
        "recipient_name": recipient_name,
        "amount": float(amount.get("value", 0)),
        "currency": amount.get("currency_code"),
        "due_date": due_date,
        "status": raw.get("status"),
        "reminders_sent": 0,
    }

