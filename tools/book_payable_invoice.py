# tools/book_payable_invoice.py

import os
import json
import base64
import requests
import logging
from datetime import datetime, timedelta
from requests import HTTPError
from dateutil.parser import parse as _parse_date
from tools.xero_accounts import ensure_account_for_category
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
    resp = requests.post(
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
    """
    Ensure a TaxRate at 'vat_rate' exists (percentage 0–100).
    Returns the TaxType.
    Retries on 401, and treats 400 as 'already exists'.
    """
    def _fetch_rates():
        headers = _get_headers()
        for attempt in range(2):
            resp = requests.get(TAXRATES_URL, headers=headers, timeout=15)
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
        resp = requests.put(TAXRATES_URL, headers=headers, json=payload, timeout=15)
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

    raise XeroToolError("Failed to create or fetch TaxRate", xero_response=resp.text)


def _validate_invoice_data(inputs: dict):
    """
    Require: invoice_number, supplier, date, total, vat_rate, line_items.
    """
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


def book_payable_invoice_tool(inputs: dict) -> dict:
    """
    Booking uses:
      - inputs['total']      : gross total (incl VAT)
      - inputs['vat_rate']   : VAT % (0–100)
      - inputs['line_items'] : each with 'amount' = net price
    """
    try:
        _validate_invoice_data(inputs)

        # 1) Dates
        try:
            invoice_date = _parse_date(inputs["date"], dayfirst=True).strftime("%Y-%m-%d")
        except Exception:
            raise XeroToolError(f"Invalid date format: {inputs['date']}")
        due_input = inputs.get("due_date")
        if due_input:
            try:
                due_date = _parse_date(due_input, dayfirst=True).strftime("%Y-%m-%d")
            except Exception:
                due_date = (datetime.strptime(invoice_date, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
        else:
            due_date = (datetime.strptime(invoice_date, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")

        # 2) Tax rate
        vat_rate = float(inputs["vat_rate"])
        tax_type = _get_or_create_tax_type(vat_rate)

        # 3) Build net line items
        items = []
        for idx, li in enumerate(inputs["line_items"]):
            # Dynamic account code assignment!
            if "category" in li:
                li["account_code"] = ensure_account_for_category(li["category"])
            account_code = li.get("account_code")
            if not account_code:
                raise XeroToolError(f"Missing account_code for line item {idx + 1}")
            try:
                items.append({
                    "Description": li.get("description", f"Item {idx + 1}"),
                    "Quantity": 1,
                    "UnitAmount": float(li["amount"]),
                    "AccountCode": account_code,
                    "TaxType": tax_type
                })
            except Exception as e:
                raise XeroToolError(f"Invalid line item {idx + 1}: {e}")

        # 4) Invoice payload (exclusive)
        payload = {
            "Invoices": [{
                "Type":            "ACCPAY",
                "Contact":         {"Name": inputs["supplier"]},
                "Date":            invoice_date,
                "DueDate":         due_date,
                "LineAmountTypes": "Exclusive",
                "LineItems":       items,
                "InvoiceNumber":   inputs["invoice_number"],
                "Reference":       inputs["invoice_number"],
                "CurrencyCode":    inputs.get("currency_code", "CHF"),
                "Status":          "DRAFT"
            }]
        }

        logger.debug("Xero payload: %s", json.dumps(payload, indent=2))

        # 5) POST with retry
        for attempt in range(3):
            headers = _get_headers()
            resp = requests.post(INVOICE_URL, headers=headers, json=payload, timeout=30)

            if resp.status_code == 401 and attempt < 2:
                _refresh_access_token(_load_tokens())
                continue
            resp.raise_for_status()
            inv = resp.json()["Invoices"][0]
            return {
                "xero_invoice_id": inv["InvoiceID"],
                "status":          inv["Status"],
                "total":           inv["Total"],
                "due_date":        inv["DueDate"],
                "reference":       inv.get("Reference")
            }

    except XeroToolError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise XeroToolError(f"System error: {e}")
