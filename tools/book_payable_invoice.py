# tools/book_payable_invoice.py

import os
import json
import base64
import requests
from datetime import datetime, timedelta

# --- Persistence files ---
TOKEN_FILE  = "/app/xero_token.json"
TENANT_FILE = "/app/xero_tenant_id.txt"

# --- Xero endpoints ---
TOKEN_URL   = "https://identity.xero.com/connect/token"
INVOICE_URL = "https://api.xero.com/api.xro/2.0/Invoices"

# --- Client credentials from env ---
CLIENT_ID     = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")

class XeroToolError(Exception):
    """Raised for any business-level error in booking invoices to Xero."""
    pass

def _save_tokens(tokens: dict):
    """Persist updated tokens back to disk."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)

def _load_tokens() -> dict:
    """Load our stored access+refresh token."""
    try:
        with open(TOKEN_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        raise XeroToolError("OAuth tokens not found: please authenticate with Xero first.")

def _refresh_access_token(tokens: dict) -> dict:
    """
    Refresh Xero OAuth2 token using the stored refresh_token.
    Raises XeroToolError("expired") if the refresh_token is invalid/expired.
    """
    if not CLIENT_ID or not CLIENT_SECRET:
        raise XeroToolError("Missing XERO_CLIENT_ID or XERO_CLIENT_SECRET environment variables")

    # Build Basic-Auth header
    creds = f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
    basic_token = base64.b64encode(creds).decode()
    headers = {
        "Authorization": f"Basic {basic_token}",
        "Content-Type":   "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type":    "refresh_token",
        "refresh_token": tokens.get("refresh_token")
    }

    resp = requests.post(TOKEN_URL, headers=headers, data=data)
    # If refresh_token is expired or invalid, Xero returns 400 + error="invalid_grant"
    if resp.status_code == 400:
        body = resp.json()
        if body.get("error") == "invalid_grant":
            # Clear out tokens so next attempt fails loudly
            try: os.remove(TOKEN_FILE)
            except OSError: pass
            raise XeroToolError(
                "Refresh token has expired or is invalid — please re-authenticate with Xero."
            )
    resp.raise_for_status()

    new_tokens = resp.json()
    tokens.update(new_tokens)
    _save_tokens(tokens)
    return tokens

def _get_headers() -> dict:
    """
    Build the Authorization + tenant headers for Xero calls.
    """
    tokens = _load_tokens()
    access_token = tokens.get("access_token")
    if not access_token:
        raise XeroToolError("No access token found – please authenticate with Xero first.")

    try:
        with open(TENANT_FILE, "r") as f:
            tenant_id = f.read().strip()
    except FileNotFoundError:
        raise XeroToolError("Xero tenant ID not found – run the OAuth flow first.")

    return {
        "Authorization":  f"Bearer {access_token}",
        "Xero-tenant-id": tenant_id,
        "Content-Type":   "application/json",
        "Accept":         "application/json",
    }

def book_payable_invoice_tool(inputs: dict) -> dict:
    """
    Book an ACCPAY invoice in Xero.
    Required inputs:
      - invoice_number: str
      - supplier:       str
      - date:           str (YYYY-MM-DD or DD/MM/YYYY)
      - line_items: [ { description, amount, account_code }, … ]
    Optional:
      - due_date:      str (same formats)
      - currency_code: str
    """
    # 1) Validate required fields
    for f in ("invoice_number", "supplier", "date", "line_items"):
        if not inputs.get(f):
            raise XeroToolError(f"Missing required field `{f}`")

    # 2) Normalize invoice date to YYYY-MM-DD
    raw = inputs["date"]
    if "/" in raw:
        d, m, y = raw.split("/")
        invoice_date = f"{y.zfill(4)}-{m.zfill(2)}-{d.zfill(2)}"
    else:
        invoice_date = raw

    # 3) Determine due date (provided or +30 days)
    raw_due = inputs.get("due_date")
    if raw_due:
        if "/" in raw_due:
            d, m, y = raw_due.split("/")
            due_date = f"{y.zfill(4)}-{m.zfill(2)}-{d.zfill(2)}"
        else:
            due_date = raw_due
    else:
        dt = datetime.strptime(invoice_date, "%Y-%m-%d")
        due_date = (dt + timedelta(days=30)).strftime("%Y-%m-%d")

    # 4) Build Xero line items
    items = []
    for li in inputs["line_items"]:
        amt  = li.get("amount")
        code = li.get("account_code")
        desc = li.get("description", "")
        if amt is None or not code:
            raise XeroToolError("Each line item needs `amount` and `account_code`")
        amt = float(amt)
        items.append({
            "Description": desc,
            "Quantity":    1,
            "UnitAmount":  amt,
            "LineAmount":  amt,
            "AccountCode": code
        })

    # 5) Assemble the payload
    payload = {
        "Invoices": [{
            "Type":            "ACCPAY",
            "Contact":         {"Name": inputs["supplier"]},
            "Date":            invoice_date,
            "DueDate":         due_date,
            "LineAmountTypes": "Exclusive",
            "LineItems":       items,
            "Reference":       inputs["invoice_number"],
            "CurrencyCode":    inputs.get("currency_code", "USD"),
        }]
    }

    # 6) POST to Xero, auto-refreshing once on 401
    for attempt in range(2):
        headers = _get_headers()
        resp = requests.post(INVOICE_URL, headers=headers, json=payload)

        if resp.status_code == 401 and attempt == 0:
            # Access token expired → refresh & retry
            _refresh_access_token(_load_tokens())
            continue

        resp.raise_for_status()
        break

    data = resp.json()
    inv  = data["Invoices"][0]
    return {
        "xero_invoice_id": inv["InvoiceID"],
        "status":          inv["Status"],
        "total":           inv["Total"],
        "due_date":        inv["DueDate"],
    }
