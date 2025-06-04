# build_prompt.py

from models import ClientContext

def build_llm_prompt(client_context: ClientContext, invoice_text: str, prompt_version: str = "v1") -> str:
    uploaded_invoices = [inv.invoice_number for inv in client_context.invoices]

    return f"""
You are an AI accounting assistant.

⚠️ Output only valid JSON.
⚠️ No markdown formatting, no backticks, no explanation.

Extract the following fields from the invoice text:
- supplier
- date (in YYYY-MM-DD format)
- invoice_number
- total (numeric, e.g., 123.45)
- vat (numeric, e.g., 25.00)
- account_category (e.g., "office supplies")

Example:
{{
  "supplier": "Amazon Ltd",
  "date": "2024-06-01",
  "invoice_number": "INV-123",
  "total": 150.00,
  "vat": 25.00,
  "account_category": "office supplies"
}}

Client State:
Step: {client_context.current_step}
Invoices: {uploaded_invoices}
Last message: {client_context.last_message}

OCR Text:
\"\"\"
{invoice_text}
\"\"\"
"""
