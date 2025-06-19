# tools/book_payable_invoice.py

import os
import json
import base64
import requests
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Constants ---
TOKEN_FILE = "/app/xero_token.json"
TENANT_FILE = "/app/xero_tenant_id.txt"

# --- Xero endpoints ---
TOKEN_URL   = "https://identity.xero.com/connect/token"
INVOICE_URL = "https://api.xero.com/api.xro/2.0/Invoices"


class XeroToolError(Exception):
    """Enhanced error class with Xero-specific details"""

    def __init__(self, message, xero_response=None):
        self.xero_response = xero_response
        super().__init__(message)


def _save_tokens(tokens: dict):
    """Thread-safe token persistence"""
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump(tokens, f)
            os.fsync(f.fileno())  # Ensure write to disk
    except Exception as e:
        logger.error(f"Failed to save tokens: {e}")
        raise XeroToolError("Token storage failed")


def _load_tokens() -> dict:
    """Safe token loading with better error handling"""
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise XeroToolError("Authentication required - no token found")
    except json.JSONDecodeError:
        raise XeroToolError("Corrupted token file - please reauthenticate")


def _refresh_access_token(tokens: dict) -> dict:
    """Enhanced token refresh with detailed error handling"""
    client_id = os.getenv("XERO_CLIENT_ID")
    client_secret = os.getenv("XERO_CLIENT_SECRET")

    if not all([client_id, client_secret]):
        raise XeroToolError("Missing Xero API credentials")

    auth_string = f"{client_id}:{client_secret}".encode()
    headers = {
        "Authorization": f"Basic {base64.b64encode(auth_string).decode()}",
        "Content-Type": "application/x-www-form-urlencoded"
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
    """Get auth headers with automatic token refresh"""
    try:
        tokens = _load_tokens()
        with open(TENANT_FILE, "r") as f:
            tenant_id = f.read().strip()
        return {
            "Authorization": f"Bearer {tokens['access_token']}",
            "Xero-tenant-id": tenant_id,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
    except Exception as e:
        logger.error(f"Header generation failed: {e}")
        raise


def _validate_invoice_data(inputs: dict):
    """Comprehensive data validation"""
    required = {
        "invoice_number": str,
        "supplier": str,
        "date": str,
        "line_items": list
    }
    for field, typ in required.items():
        if not isinstance(inputs.get(field), typ):
            raise XeroToolError(f"Invalid type for {field} - expected {typ.__name__}")
    if not inputs["line_items"]:
        raise XeroToolError("At least one line item required")


def book_payable_invoice_tool(inputs: dict) -> dict:
    """
    Enhanced invoice booking with:
    - Better validation
    - CHF currency default
    - Detailed error handling
    - **Sets InvoiceNumber** so it shows up in Xero UI
    """
    try:
        _validate_invoice_data(inputs)

        # Date handling
        invoice_date = (
            datetime.strptime(inputs["date"], "%d.%m.%Y").strftime("%Y-%m-%d")
            if "." in inputs["date"] else inputs["date"]
        )
        due_date = (
            datetime.strptime(inputs["due_date"], "%d.%m.%Y").strftime("%Y-%m-%d")
            if inputs.get("due_date") and "." in inputs["due_date"]
            else (datetime.strptime(invoice_date, "%Y-%m-%d") + timedelta(days=30)).strftime("%Y-%m-%d")
        )

        # Line items
        items = []
        for idx, li in enumerate(inputs["line_items"]):
            try:
                items.append({
                    "Description": li.get("description", f"Item {idx + 1}"),
                    "Quantity": 1,
                    "UnitAmount": float(li["amount"]),
                    "AccountCode": li["account_code"],
                    "TaxType": "INPUT"
                })
            except (KeyError, ValueError) as e:
                raise XeroToolError(f"Invalid line item {idx + 1}: {e}")

        # Build payload
        payload = {
            "Invoices": [{
                "Type":            "ACCPAY",
                "Contact":         {"Name": inputs["supplier"]},
                "Date":            invoice_date,
                "DueDate":         due_date,
                "LineAmountTypes": "Inclusive",
                "LineItems":       items,
                "InvoiceNumber":   inputs["invoice_number"],   # ← **THIS** is the bill # field
                "Reference":       inputs["invoice_number"],   # optional, your choice
                "CurrencyCode":    inputs.get("currency_code", "CHF"),
                "Status":          "DRAFT"
            }]
        }

        logger.debug("Xero payload: %s", json.dumps(payload, indent=2))

        # API request with retries
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
