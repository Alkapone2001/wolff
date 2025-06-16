import os
import json
import requests

TOKEN_FILE  = "/app/xero_token.json"
TENANT_FILE = "/app/xero_tenant_id.txt"

def _load_headers():
    tokens = json.load(open(TOKEN_FILE))
    tenant = open(TENANT_FILE).read().strip()
    return {
        "Authorization": f"Bearer {tokens['access_token']}",
        "Xero-tenant-id": tenant,
        "Content-Type": "application/json",
        "Accept": "application/json"       # ← ask Xero to return JSON
    }

def book_payable_invoice_tool(inputs: dict) -> dict:
    """
    inputs: {
      invoice_number, supplier,
      date, due_date,
      line_items: [ {description, amount, account_code}, … ],
      currency_code
    }
    """
    hdr = _load_headers()
    # Build line-items payload
    items = [{
        "Description": li["description"],
        "Quantity": 1,
        "UnitAmount": li["amount"],
        "AccountCode": li["account_code"]
    } for li in inputs["line_items"]]

    body = {
        "Invoices": [{
            "Type": "ACCPAY",
            "Contact": {"Name": inputs["supplier"]},
            "Date": inputs["date"],
            "DueDate": inputs["due_date"],
            "LineItems": items,
            "Reference": inputs["invoice_number"],
            "CurrencyCode": inputs.get("currency_code", "USD")
        }]
    }

    # use `json=` so requests also sets Content-Type JSON for us
    resp = requests.post(
        "https://api.xero.com/api.xro/2.0/Invoices",
        headers=hdr,
        json=body
    )
    resp.raise_for_status()

    # now Xero will return JSON
    inv = resp.json()["Invoices"][0]
    return {
        "xero_invoice_id": inv["InvoiceID"],
        "status":           inv["Status"],
        "total":            inv["Total"],
        "due_date":         inv["DueDate"]
    }
