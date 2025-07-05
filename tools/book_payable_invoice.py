# tools/book_payable_invoice.py

import os
import json
import base64
import logging
import anyio
import asyncio
import httpx
from datetime import datetime, timedelta
from dateutil.parser import parse as _parse_date
from requests import HTTPError
from .xero_accounts import ensure_account_for_category_existing_only
from .xero_utils import _get_headers, XeroToolError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Constants ---
TOKEN_FILE     = "/app/xero_token.json"
TENANT_FILE    = "/app/xero_tenant_id.txt"
TOKEN_URL      = "https://identity.xero.com/connect/token"
INVOICE_URL    = "https://api.xero.com/api.xro/2.0/Invoices"
TAXRATES_URL   = "https://api.xero.com/api.xro/2.0/TaxRates"
ATTACHMENT_URL_FMT = "https://api.xero.com/api.xro/2.0/Invoices/{invoice_id}/Attachments/{filename}"

# INTEGRATION REQUIREMENT:
# You MUST have `accounting.attachments` in your Xero app scopes, AND you must re-authenticate
# after adding it. Otherwise, attachments will always return 401 Unauthorized.

class XeroToolError(Exception):
    def __init__(self, message, xero_response=None):
        self.xero_response = xero_response
        super().__init__(message)

def _save_tokens(tokens: dict):
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)
            os.fsync(f.fileno())
    except Exception as e:
        logger.error(f"Failed to save tokens: {e}")
        raise XeroToolError("Token storage failed")

def _load_tokens() -> dict:
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise XeroToolError("Authentication required - no token found")
    except json.JSONDecodeError:
        raise XeroToolError("Corrupted token file - please reauthenticate")

def _refresh_access_token(tokens: dict) -> dict:
    client_id = os.getenv("XERO_CLIENT_ID")
    client_secret = os.getenv("XERO_CLIENT_SECRET")
    if not all([client_id, client_secret]):
        raise XeroToolError("Missing Xero API credentials")
    auth = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type":  "application/x-www-form-urlencoded"
    }
    resp = httpx.post(
        TOKEN_URL,
        headers=headers,
        data={"grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]}
    )
    if resp.status_code == 400 and resp.json().get("error") == "invalid_grant":
        os.remove(TOKEN_FILE)
        raise XeroToolError("Refresh token expired - please reauthenticate")
    resp.raise_for_status()
    new_tokens = resp.json()
    _save_tokens(new_tokens)
    return new_tokens

def _get_headers() -> dict:
    tokens = _load_tokens()
    with open(TENANT_FILE, "r") as f:
        tenant_id = f.read().strip()
    return {
        "Authorization":   f"Bearer {tokens['access_token']}",
        "Xero-tenant-id":  tenant_id,
        "Content-Type":    "application/json",
        "Accept":          "application/json"
    }

def _get_or_create_tax_type(vat_rate: float) -> str:
    def _fetch_rates():
        headers = _get_headers()
        for attempt in range(2):
            resp = httpx.get(TAXRATES_URL, headers=headers, timeout=15)
            if resp.status_code == 401 and attempt == 0:
                _refresh_access_token(_load_tokens())
                headers = _get_headers()
                continue
            resp.raise_for_status()
            return resp.json().get("TaxRates", [])
        raise XeroToolError("Unauthorized fetching TaxRates", xero_response=resp.text)

    existing = _fetch_rates()
    for tr in existing:
        for comp in tr.get("TaxComponents", []):
            if abs(comp.get("Rate", 0) - vat_rate) < 1e-6:
                return tr["TaxType"]

    name = f"Expenses {vat_rate}%"
    payload = {
        "TaxRates": [{
            "Name":          name,
            "TaxComponents": [{
                "Name":  name,
                "Rate":  vat_rate,
                "Type":  "INPUT"
            }],
            "Status":        "ACTIVE"
        }]
    }

    headers = _get_headers()
    for attempt in range(2):
        resp = httpx.put(TAXRATES_URL, headers=headers, json=payload, timeout=15)
        if resp.status_code == 401 and attempt == 0:
            _refresh_access_token(_load_tokens())
            headers = _get_headers()
            continue
        try:
            resp.raise_for_status()
        except HTTPError:
            if resp.status_code == 400:
                existing = _fetch_rates()
                for tr in existing:
                    for comp in tr.get("TaxComponents", []):
                        if abs(comp.get("Rate", 0) - vat_rate) < 1e-6:
                            return tr["TaxType"]
            raise XeroToolError(f"Error creating TaxRate: {resp.text}", xero_response=resp.text)
        created = resp.json()["TaxRates"][0]
        return created["TaxType"]

    raise XeroToolError("Failed to create or fetch TaxRate", xero_response="")

def _validate_invoice_data(inputs: dict):
    required = ["invoice_number", "supplier", "date", "total", "vat_rate", "line_items"]
    for key in required:
        if key not in inputs or inputs[key] is None:
            raise XeroToolError(f"Missing required field: {key}")
    if not isinstance(inputs["invoice_number"], str):
        raise XeroToolError("Invalid type for invoice_number - expected str")
    if not isinstance(inputs["supplier"], str):
        raise XeroToolError("Invalid type for supplier - expected str")
    if not isinstance(inputs["date"], str):
        raise XeroToolError("Invalid type for date - expected str")
    if not isinstance(inputs["total"], (int, float, str)):
        raise XeroToolError("Invalid type for total - expected number or numeric string")
    if not isinstance(inputs["vat_rate"], (int, float, str)):
        raise XeroToolError("Invalid type for vat_rate - expected number or numeric string")
    if not isinstance(inputs["line_items"], list) or not inputs["line_items"]:
        raise XeroToolError("At least one line item required")

async def book_payable_invoice_tool(inputs: dict) -> dict:
    await anyio.to_thread.run_sync(_validate_invoice_data, inputs)

    try:
        invoice_dt = _parse_date(inputs["date"], dayfirst=True)
    except Exception:
        raise XeroToolError(f"Invalid date format: {inputs['date']}")
    due_input = inputs.get("due_date")
    if due_input:
        try:
            due_dt = _parse_date(due_input, dayfirst=True)
        except Exception:
            due_dt = invoice_dt + timedelta(days=30)
    else:
        due_dt = invoice_dt + timedelta(days=30)

    vat_rate = float(inputs["vat_rate"])
    if vat_rate == 0:
        tax_type = "NONE"
    else:
        tax_type = await anyio.to_thread.run_sync(_get_or_create_tax_type, vat_rate)

    async def resolve_line_item(li):
        category = li.get("category") or "General Expenses"
        acct_code = await ensure_account_for_category_existing_only(category)
        logger.info(f"USING AccountCode {acct_code} for category '{category}'")
        return {
            "Description": li.get("description", ""),
            "Quantity": 1,
            "UnitAmount": float(li["amount"]),
            "AccountCode": acct_code,
            "TaxType": tax_type
        }

    items = await asyncio.gather(*[resolve_line_item(li) for li in inputs["line_items"]])

    payload = {
        "Invoices": [{
            "Type":            "ACCPAY",
            "Contact":         {"Name": inputs["supplier"]},
            "Date":            invoice_dt.strftime("%Y-%m-%d"),
            "DueDate":         due_dt.strftime("%Y-%m-%d"),
            "LineAmountTypes": "Exclusive",
            "LineItems":       items,
            "InvoiceNumber":   inputs["invoice_number"],
            "Reference":       inputs["invoice_number"],
            "CurrencyCode":    inputs.get("currency_code", "CHF"),
            "Status":          "DRAFT"
        }]
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(INVOICE_URL, headers=_get_headers(), json=payload)
        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text
            raise XeroToolError(
                f"Xero API error {resp.status_code}: {error_body}",
                xero_response=error_body
            ) from e
        inv = resp.json()["Invoices"][0]

        # --- PDF Attachment upload step ---
        attachment_result = None
        pdf_bytes_b64 = inputs.get("pdf_bytes")
        if pdf_bytes_b64:
            try:
                pdf_bytes = base64.b64decode(pdf_bytes_b64)
                invoice_id = inv["InvoiceID"]
                filename = f"Invoice_{inv['InvoiceNumber']}.pdf"
                attachment_url = ATTACHMENT_URL_FMT.format(invoice_id=invoice_id, filename=filename)

                await asyncio.sleep(1)  # Xero may be eventually consistent

                # Always use fresh headers and required keys only
                attach_headers_raw = _get_headers()
                attach_headers = {
                    "Authorization":   attach_headers_raw["Authorization"],
                    "Xero-tenant-id":  attach_headers_raw["Xero-tenant-id"],
                    "Content-Type":    "application/pdf"
                }

                print("\n\n=== Xero Attachment Upload Debug ===")
                print("Xero Attach Headers (without token):", {k: (v[:15]+"...") if k == "Authorization" else v for k,v in attach_headers.items()})
                print("Xero Attach URL:", attachment_url)
                print("Xero Attach PDF size:", len(pdf_bytes))
                print("Reminder: You MUST have 'accounting.attachments' in your Xero app scopes and be authenticated with a token that includes it!\n")

                async with httpx.AsyncClient(timeout=30) as attach_client:
                    attach_resp = await attach_client.put(
                        attachment_url,
                        headers=attach_headers,
                        content=pdf_bytes
                    )

                print("Xero Attach Response:", attach_resp.status_code, attach_resp.text)
                logger.info(f"Attachment PUT response: {attach_resp.status_code}, body: {attach_resp.text}")

                try:
                    attach_resp.raise_for_status()
                    attachment_result = {"attachment_status": "uploaded", "file_name": filename}
                except httpx.HTTPStatusError:
                    attachment_result = {
                        "attachment_status": "failed",
                        "error": attach_resp.text,
                        "response_status": attach_resp.status_code
                    }
            except Exception as ex:
                attachment_result = {"attachment_status": "failed", "error": str(ex)}

        result = {
            "xero_invoice_id": inv["InvoiceID"],
            "status":          inv["Status"],
            "total":           inv["Total"],
            "due_date":        inv["DueDate"],
            "reference":       inv.get("Reference"),
        }
        if attachment_result:
            result.update(attachment_result)
        return result
