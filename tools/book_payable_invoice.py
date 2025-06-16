# tools/book_payable_invoice.py

import os
import json
import requests
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth

# Paths where we persist tokens + tenant ID
TOKEN_FILE  = "/app/xero_token.json"
TENANT_FILE = "/app/xero_tenant_id.txt"

# Xero endpoints
TOKEN_URL   = "https://identity.xero.com/connect/token"
INVOICE_URL = "https://api.xero.com/api.xro/2.0/Invoices"

# Client credentials from environment
CLIENT_ID     = os.getenv("XERO_CLIENT_ID")
CLIENT_SECRET = os.getenv("XERO_CLIENT_SECRET")
REDIRECT_URI  = os.getenv("XERO_REDIRECT_URI")

def _save_tokens(tokens: dict):
    """Persist updated tokens back to disk."""
    with open(TOKEN_FILE, "w") as f:
        json.dump(tokens, f)

def _load_tokens() -> dict:
    """Load our stored access+refresh token."""
    with open(TOKEN_FILE, "r") as f:
        return json.load(f)

def _refresh_access_token(tokens: dict) -> dict:
    """
    When Xero returns 401, call this to refresh and re-save tokens.
    """
    data = {
        "grant_type":    "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "redirect_uri":  REDIRECT_URI,
    }
    resp = requests.post(
        TOKEN_URL,
        auth=HTTPBasicAuth(CLIENT_ID, CLIENT_SECRET),
        data=data,
    )
    resp.raise_for_status()
    new_tokens = resp.json()
    tokens.update(new_tokens)
    _save_tokens(tokens)
    return tokens

def _get_headers() -> dict:
    """
    Build the Authorization + tenant headers for Xero.
    """
    tokens = _load_tokens()
    return {
        "Authorization":  f"Bearer {tokens['access_token']}",
        "Xero-tenant-id": open(TENANT_FILE, "r").read().strip(),
        "Content-Type":   "application/json",
        "Accept":         "application/json",
    }

class XeroToolError(Exception):
    pass

def book_payable_invoice_tool(inputs: dict) -> dict:
    """
    inputs {
      invoice_number: str,
      supplier:       str,
      date:           str,  # YYYY-MM-DD or DD/MM/YYYY
      due_date?:      str,  # same formats, optional
      line_items: [ { description, amount, account_code }, … ],
      currency_code?: str
    }
    """
    # 1) Required fields
    for f in ("invoice_number", "supplier", "date", "line_items"):
        if not inputs.get(f):
            raise XeroToolError(f"Missing required field `{f}`")

    # 2) Normalize invoice date
    raw = inputs["date"]
    if "/" in raw:
        d, m, y = raw.split("/")
        invoice_date = f"{y.zfill(4)}-{m.zfill(2)}-{d.zfill(2)}"
    else:
        invoice_date = raw

    # 3) Normalize or default due_date (+30 days)
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

    # 4) Build line items (must supply both UnitAmount & LineAmount)
    items = []
    for li in inputs["line_items"]:
        desc = li.get("description", "")
        amt  = li.get("amount")
        code = li.get("account_code")
        if amt is None or not code:
            raise XeroToolError("Each line item needs `amount` and `account_code`")
        amt = float(amt)
        items.append({
            "Description":  desc,
            "Quantity":     1,
            "UnitAmount":   amt,
            "LineAmount":   amt,
            "AccountCode":  code
        })

    # 5) Assemble payload
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

    # 6) POST + auto-refresh on 401
    for attempt in (1, 2):
        headers = _get_headers()
        resp    = requests.post(INVOICE_URL, headers=headers, json=payload)
        if resp.status_code == 401 and attempt == 1:
            # token expired → refresh and retry once
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
